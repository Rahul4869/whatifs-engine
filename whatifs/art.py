"""whatifs/art.py v7.0 - thumbnails + reel covers: premium key art, cinematic grade, bold type with stroke + glow,
phone-size readability check, brand mark. 3840x2160 master, 1280x720 upload (<2MB)."""
from __future__ import annotations
import os, numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageOps
from whatifs.media import still, font

def _grade(im):
    im = ImageEnhance.Contrast(im).enhance(1.18); im = ImageEnhance.Color(im).enhance(1.22); im = ImageEnhance.Sharpness(im).enhance(1.3)
    w, h = im.size; yy, xx = np.mgrid[0:h, 0:w]
    v = 1 - 0.55 * (((xx - w / 2) / (w / 1.4)) ** 2 + ((yy - h / 2) / (h / 1.4)) ** 2)
    a = np.asarray(im, np.float32) * v.clip(0.35, 1)[..., None]
    return Image.fromarray(a.clip(0, 255).astype(np.uint8))

def _wrap(text, f, d, maxw):
    words, lines, cur = text.split(), [], ""
    for wd in words:
        t = (cur + " " + wd).strip()
        if d.textlength(t, font=f) <= maxw or not cur: cur = t
        else: lines.append(cur); cur = wd
    if cur: lines.append(cur)
    return lines

def _type(im, text, side="left", accent=(255, 214, 0), vertical=False):
    W, H = im.size; text = (text or "").upper().strip()
    if not text: return im
    size = int(H * (0.12 if vertical else 0.2)); maxw = W * (0.86 if vertical else 0.52)
    d = ImageDraw.Draw(im)
    while size > 20:
        f = font(size); lines = _wrap(text, f, d, maxw)
        if len(lines) <= 3: break
        size = int(size * 0.9)
    lh = int(size * 1.02); block = lh * len(lines)
    x = W * 0.05 if side == "left" and not vertical else None
    y = H * (0.07 if vertical else 0.5 - block / (2 * H) * 1.0 if False else (H - block) / 2 / H)
    y = int(H * 0.08) if vertical else int((H - block) / 2)
    glow = Image.new("RGBA", im.size, (0, 0, 0, 0)); g = ImageDraw.Draw(glow); top = Image.new("RGBA", im.size, (0, 0, 0, 0)); t = ImageDraw.Draw(top)
    for i, ln in enumerate(lines):
        lw = t.textlength(ln, font=f); xx = (W - lw) / 2 if x is None else x; yy = y + i * lh
        col = accent if i == len(lines) - 1 else (255, 255, 255)
        g.text((xx, yy), ln, font=f, fill=(0, 0, 0, 255), stroke_width=int(size * 0.16), stroke_fill=(0, 0, 0, 255))
        t.text((xx, yy), ln, font=f, fill=col + (255,), stroke_width=int(size * 0.05), stroke_fill=(0, 0, 0, 255))
    glow = glow.filter(ImageFilter.GaussianBlur(size * 0.12))
    out = Image.alpha_composite(im.convert("RGBA"), glow); out = Image.alpha_composite(out, top)
    return out.convert("RGB")

def _brand(im):
    W, H = im.size; d = ImageDraw.Draw(im); f = font(int(H * 0.035))
    d.text((W - W * 0.02 - d.textlength("WHAT IFS", font=f), H * 0.93), "WHAT IFS", font=f, fill=(255, 255, 255), stroke_width=2, stroke_fill=(0, 0, 0))
    return im

def phone_check(im):
    """Readability at phone size: text block contrast at 168x94."""
    small = ImageOps.grayscale(im.resize((168, 94))); a = np.asarray(small, np.float32)
    return float(a.std())

def thumbnail(prompt, text, out_dir, episode, side="left"):
    os.makedirs(out_dir, exist_ok=True)
    full = prompt + ". Ultra-detailed cinematic key art, one dramatic focal subject placed on the " + ("right" if side == "left" else "left") + \
           " two-thirds, strong rim light, deep contrast, volumetric haze, 8k detail, no text, no letters, no logos, no watermark"
    raw, _ = still(full, os.path.join(out_dir, "thumb_raw.jpg"), episode, seed=episode + "thumb", w=1920, h=1080, premium=True)
    im = Image.open(raw).convert("RGB").resize((3840, 2160), Image.LANCZOS)
    im = _brand(_type(_grade(im), text, side))
    master = os.path.join(out_dir, "thumb_master.jpg"); im.save(master, quality=95)
    up = os.path.join(out_dir, "thumb.jpg"); q = 92
    small = im.resize((1280, 720), Image.LANCZOS)
    while True:
        small.save(up, quality=q, optimize=True)
        if os.path.getsize(up) < 1_900_000 or q < 60: break
        q -= 6
    return up, master, phone_check(small)

def reel_cover(prompt, text, out_dir, episode, k):
    full = prompt + ". Vertical 9:16 cinematic key art, dramatic subject in lower half, empty dark sky in top third, 8k detail, no text, no letters"
    raw, _ = still(full, os.path.join(out_dir, f"cover{k}_raw.jpg"), episode, seed=f"{episode}cover{k}", w=1080, h=1920, premium=True)
    im = Image.open(raw).convert("RGB").resize((1080, 1920), Image.LANCZOS)
    im = _brand(_type(_grade(im), text, vertical=True))
    p = os.path.join(out_dir, f"cover{k}.jpg"); im.save(p, quality=93); return p
