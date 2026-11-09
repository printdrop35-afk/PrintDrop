"""Builds every PrintDrop brand asset from the official logo (brand/source/logo-original.webp).

Raster variants keep the original artwork pixel-for-pixel (only recoloured, never stretched).
Vector variants: a hand-built SVG icon redrawn from the original mark + an outlined wordmark
(Outfit 800, converted to paths so it renders identically everywhere).
Run:  python /app/brand/build_brand.py
"""

from pathlib import Path

from PIL import Image

SRC = Path(__file__).parent / "source" / "logo-original.webp"
OUT = Path("/app/frontend/public/brand")
PUB = Path("/app/frontend/public/brand/favicon")  # copied to /public on approval (Stage 5)
PUB.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)

NAVY, BLUE, CYAN, WHITE, DARK = (9, 38, 92), (8, 104, 239), (8, 187, 208), (255, 255, 255), (7, 26, 61)

img = Image.open(SRC).convert("RGBA")
img = img.crop(img.getchannel("A").point(lambda a: 255 if a > 12 else 0).getbbox())  # trim, keep ratio
W, H = img.size
MARK_W = int(W * 0.288)  # document + pixels, cut just before the "P" (swoosh tip trimmed)


def is_navy(r: int, g: int, b: int) -> bool:
    return r < 40 and g < 90 and b < 175 and (b - g) > 25


def recolor(src: Image.Image, fn) -> Image.Image:
    out = src.copy()
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            if a:
                px[x, y] = (*fn(r, g, b), a)
    return out


def pad_square(src: Image.Image, pad: float = 0.08) -> Image.Image:
    side = int(max(src.size) * (1 + pad * 2))
    sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.alpha_composite(src, ((side - src.width) // 2, (side - src.height) // 2))
    return sq


def save_png(im: Image.Image, name: str, width: int | None = None) -> None:
    if width:
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)  # proportional only
    im.save(OUT / name, optimize=True)


light = img
dark = recolor(img, lambda r, g, b: WHITE if is_navy(r, g, b) else (r, g, b))
mono_navy = recolor(img, lambda r, g, b: NAVY)
mono_white = recolor(img, lambda r, g, b: WHITE)

for nm, im in {"light": light, "dark": dark, "mono-navy": mono_navy, "mono-white": mono_white}.items():
    save_png(im, f"printdrop-logo-{nm}.png", 1600)
    save_png(im, f"printdrop-logo-{nm}@1x.png", 480)
    mark = im.crop((0, 0, MARK_W, H))
    save_png(pad_square(mark), f"printdrop-icon-{nm}.png", 512)

# ---------- vector icon (redrawn from the original mark) ----------
ICON_BODY = f"""
  <defs>
    <linearGradient id="pdFold" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#08BBD0"/><stop offset="1" stop-color="#0868EF"/></linearGradient>
    <linearGradient id="pdSwoosh" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="{{navy}}"/><stop offset="1" stop-color="#08BBD0"/></linearGradient>
  </defs>
  <rect x="3" y="17" width="4" height="4" rx="0.6" fill="#08BBD0"/>
  <rect x="0.5" y="25" width="4.5" height="4.5" rx="0.6" fill="#0868EF"/>
  <rect x="7.5" y="23" width="4.5" height="4.5" rx="0.6" fill="#1B8FEA"/>
  <rect x="5" y="31" width="5.5" height="5.5" rx="0.7" fill="#0A7BE8"/>
  <rect x="0" y="34" width="3.5" height="3.5" rx="0.5" fill="{{navy}}"/>
  <rect x="9" y="38" width="4.5" height="4.5" rx="0.6" fill="#08BBD0"/>
  <rect x="6.5" y="45" width="3.5" height="3.5" rx="0.5" fill="#08BBD0"/>
  <path d="M19 52 V14 a6 6 0 0 1 6 -6 H43 L54 19 V49" fill="none" stroke="{{navy}}" stroke-width="3.6" stroke-linejoin="round" stroke-linecap="round"/>
  <path d="M43 8 V15 a4 4 0 0 0 4 4 H54 Z" fill="url(#pdFold)"/>
  <g fill="none" stroke="{{navy}}" stroke-width="1.8">
    <rect x="24.4" y="23.4" width="7.2" height="7.2"/><rect x="38.4" y="23.4" width="7.2" height="7.2"/><rect x="24.4" y="37.4" width="7.2" height="7.2"/>
  </g>
  <g fill="{{navy}}"><rect x="26.8" y="25.8" width="2.4" height="2.4"/><rect x="40.8" y="25.8" width="2.4" height="2.4"/><rect x="26.8" y="39.8" width="2.4" height="2.4"/>
    <rect x="34" y="36" width="2.6" height="2.6"/><rect x="38.4" y="34.4" width="2.6" height="2.6"/><rect x="42.8" y="36" width="2.6" height="2.6"/><rect x="36.2" y="40.4" width="2.6" height="2.6"/><rect x="41" y="42" width="2.6" height="2.6"/></g>
  <g fill="#0868EF"><rect x="33.6" y="23" width="2.8" height="3.6"/><rect x="33.6" y="28" width="2.8" height="3.6"/><rect x="24" y="33.4" width="4" height="2.6"/><rect x="33.6" y="44" width="2.8" height="2.6"/></g>
  <rect x="30" y="33.6" width="2" height="2" fill="#08BBD0"/>
  <path d="M8 60 C26 58 42 53 60 43 C44 50 28 55.5 8 60 Z" fill="url(#pdSwoosh)"/>
"""


def icon_svg(navy: str = "#09265C", bg: str | None = None) -> str:
    rect = f'<rect width="64" height="64" rx="14" fill="{bg}"/>' if bg else ""
    inner = ICON_BODY.replace("{navy}", navy)
    body = f'<g transform="translate(5 3) scale(0.86)">{inner}</g>' if bg else inner
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="PrintDrop">{rect}{body}</svg>\n'


(OUT / "printdrop-icon.svg").write_text(icon_svg())
(OUT / "printdrop-icon-dark.svg").write_text(icon_svg(navy="#FFFFFF"))
(OUT / "printdrop-icon-mono.svg").write_text(icon_svg().replace("#08BBD0", "#09265C").replace("#0868EF", "#09265C").replace("#1B8FEA", "#09265C").replace("#0A7BE8", "#09265C"))
(OUT / "printdrop-app-icon.svg").write_text(icon_svg(navy="#FFFFFF", bg="#09265C"))
(PUB / "favicon.svg").write_text(icon_svg(navy="#FFFFFF", bg="#09265C"))

# ---------- vector wordmark (Outfit 800 → outlines) ----------
try:
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont

    font = TTFont("/app/frontend/node_modules/@fontsource-variable/outfit/files/outfit-latin-wght-normal.woff2")
    font = instantiateVariableFont(font, {"wght": 800})
    gs, cmap, upm = font.getGlyphSet(), font.getBestCmap(), font["head"].unitsPerEm
    asc = font["hhea"].ascent

    def word(text: str, x0: float) -> tuple[str, float]:
        pen = SVGPathPen(gs)
        x = x0
        for ch in text:
            g = cmap[ord(ch)]
            gs[g].draw(TransformPen(pen, (1, 0, 0, -1, x, asc)))
            x += gs[g].width - 8  # slight tightening like the original wordmark
        return pen.getCommands(), x

    p1, x1 = word("Print", 0)
    p2, x2 = word("Drop", x1)
    scale = 46 / upm
    wm_w = x2 * scale

    def full_svg(print_fill: str) -> str:
        total_w = 72 + wm_w
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total_w:.1f} 64" role="img" aria-label="PrintDrop">'
                f'<defs><linearGradient id="pdWord" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#0868EF"/><stop offset="1" stop-color="#08BBD0"/></linearGradient></defs>'
                f'{icon_svg(navy=print_fill).split(">", 1)[1].rsplit("</svg>", 1)[0]}'
                f'<g transform="translate(70 -1) scale({scale:.5f})"><path d="{p1}" fill="{print_fill}"/>'
                f'<path d="{p2}" fill="url(#pdWord)"/></g></svg>\n')

    (OUT / "printdrop-logo.svg").write_text(full_svg("#09265C"))
    (OUT / "printdrop-logo-dark.svg").write_text(full_svg("#FFFFFF"))
    (OUT / "printdrop-logo-mono.svg").write_text(full_svg("#09265C").replace("url(#pdWord)", "#09265C").replace("#08BBD0", "#09265C").replace("#0868EF", "#09265C").replace("#1B8FEA", "#09265C").replace("#0A7BE8", "#09265C"))
    print("vector wordmark ok")
except Exception as e:  # raster logos remain the official reference
    print("vector wordmark skipped:", e)

# ---------- favicons & app icons (from the original mark on navy, never stretched) ----------
mark_dark = pad_square(dark.crop((0, 0, MARK_W, H)), 0.12)


def tile(size: int, radius_ratio: float = 0.22) -> Image.Image:
    base = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    from PIL import ImageDraw
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, size - 1, size - 1), radius=int(size * radius_ratio), fill=255)
    navy = Image.new("RGBA", (size, size), (*NAVY, 255))
    base.paste(navy, (0, 0), m)
    base.alpha_composite(mark_dark.resize((size, size), Image.LANCZOS))
    return base


for s, name in [(16, "favicon-16x16.png"), (32, "favicon-32x32.png"), (180, "apple-touch-icon.png")]:
    tile(s, 0.0 if s == 180 else 0.22).save(PUB / name)
for s in (192, 512):
    tile(s).save(OUT / f"printdrop-app-icon-{s}.png")
tile(48).save(PUB / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])

# Open Graph image 1200x630 (dark brand surface + dark logo)
og = Image.new("RGBA", (1200, 630), (*DARK, 255))
lg = dark.resize((900, round(dark.height * 900 / dark.width)), Image.LANCZOS)
og.alpha_composite(lg, ((1200 - lg.width) // 2, (630 - lg.height) // 2 - 30))
og.convert("RGB").save(OUT / "printdrop-og.png", optimize=True)
print("assets:", sorted(p.name for p in OUT.iterdir()))
