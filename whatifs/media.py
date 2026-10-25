"""whatifs/media.py v7.0 - fal.ai images/clips, free NASA/Pexels footage, depth maps, motion graphics, fake assets for rehearsal."""
from __future__ import annotations
import os, time, json, hashlib, random, subprocess
import numpy as np, requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from whatifs.core import env, log, cost, S, FAKE, WORK
from whatifs.governor import fal_allowed

FAL = "https://queue.fal.run/"
def FH(): return {"Authorization": "Key " + env("FAL_KEY"), "Content-Type": "application/json"}

def fal_run(model_id, args, timeout=900):
    r = requests.post(FAL + model_id, headers=FH(), json=args, timeout=60)
    if r.status_code >= 400: raise RuntimeError(f"fal submit {r.status_code}: {r.text[:300]}")
    j = r.json(); st_url, res_url = j.get("status_url"), j.get("response_url")
    t0 = time.time()
    while time.time() - t0 < timeout:
        s = requests.get(st_url, headers=FH(), timeout=30).json()
        if s.get("status") == "COMPLETED": break
        if s.get("status") in ("FAILED", "ERROR"): raise RuntimeError(f"fal failed: {s}")
        time.sleep(3)
    else: raise RuntimeError("fal timeout")
    return requests.get(res_url, headers=FH(), timeout=60).json()

def _dl(url, path):
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for c in r.iter_content(1 << 20): f.write(c)
    return path

# ---------------- fake assets (rehearsal) ----------------
def fake_image(path, w, h, seed, label=""):
    rng = random.Random(seed); img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    c1 = (rng.randint(0, 60), rng.randint(20, 90), rng.randint(60, 140)); c2 = (rng.randint(150, 255), rng.randint(80, 180), rng.randint(20, 90))
    for y in range(h):
        k = y / h; d.line([(0, y), (w, y)], fill=tuple(int(c1[i] * (1 - k) + c2[i] * k) for i in range(3)))
    for _ in range(18):
        x, y, r = rng.randint(0, w), rng.randint(0, h), rng.randint(h // 30, h // 6)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(rng.randint(0, 255), rng.randint(0, 255), rng.randint(0, 255)))
    img = img.filter(ImageFilter.GaussianBlur(2))
    if label: ImageDraw.Draw(img).text((20, 20), label[:60], fill=(255, 255, 255))
    img.save(path, quality=92); return path

def fake_clip(path, w, h, seed, sec=5):
    img = fake_image(path + ".jpg", w, h, seed)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", img, "-t", str(sec), "-vf",
                    f"scale={w*1.1:.0f}:-2,crop={w}:{h}:'(iw-ow)/2+sin(t)*20':'(ih-oh)/2',format=yuv420p", "-r", "30", path], check=True)
    os.remove(img); return path

# ---------------- images ----------------
def still(prompt, path, episode, seed=None, w=None, h=None, premium=False):
    w = w or S("STILL_W", int); h = h or S("STILL_H", int)
    if FAKE: return fake_image(path, w, h, seed or prompt, prompt), None
    if not fal_allowed(): raise RuntimeError("fal credit exhausted")
    model = S("FAL_PREMIUM_MODEL") if premium else S("FAL_STILL_MODEL")
    args = {"prompt": prompt, "image_size": {"width": w, "height": h}, "num_images": 1, "enable_safety_checker": True}
    if not premium: args["num_inference_steps"] = 4
    else: args["safety_tolerance"] = "2"
    if seed is not None: args["seed"] = int(hashlib.md5(str(seed).encode()).hexdigest()[:7], 16)
    out = fal_run(model, args)
    url = out["images"][0]["url"]; _dl(url, path)
    mp = w * h / 1e6
    cost("image_premium" if premium else "image", "fal", 1, (S("PRICE_THUMB_USD", float) if premium else S("PRICE_STILL_USD", float) * mp / 1.5), episode)
    return path, url

def animate(image_url, image_path, prompt, path, episode, hero=False):
    if FAKE or not image_url: return fake_clip(path, S("STILL_W", int), S("STILL_H", int), prompt, 5)
    if not fal_allowed(): raise RuntimeError("fal credit exhausted")
    model = S("FAL_HERO_MODEL") if hero else S("FAL_LIVING_MODEL")
    args = {"prompt": prompt, "image_url": image_url}
    if hero: args.update({"duration": "5", "negative_prompt": "blur, distort, low quality, text, watermark"})
    out = fal_run(model, args, timeout=1500)
    url = (out.get("video") or {}).get("url")
    if not url: raise RuntimeError(f"no video in fal reply: {str(out)[:200]}")
    _dl(url, path)
    cost("hero_clip" if hero else "living_clip", "fal", 1, S("PRICE_KLING_USD", float) if hero else S("PRICE_LIVING_USD", float), episode)
    return path

# ---------------- free real footage ----------------
def stock(query, path, episode):
    if FAKE: return fake_clip(path, 1280, 720, query, 6)
    for fn in (_nasa, _pexels):
        try:
            if fn(query, path): return path
        except Exception as e: log(f"stock {fn.__name__} failed: {e}", "WARN", episode)
    return None

def _nasa(q, path):
    r = requests.get("https://images-api.nasa.gov/search", params={"q": q, "media_type": "video"}, timeout=30).json()
    for it in r.get("collection", {}).get("items", [])[:8]:
        d = (it.get("data") or [{}])[0]
        if "copyright" in json.dumps(d).lower(): continue
        files = requests.get(it["href"], timeout=30).json()
        mp4 = [f for f in files if f.endswith(".mp4")]
        pick = next((f for f in mp4 if "~medium" in f), None) or next((f for f in mp4 if "~mobile" in f), None) or (mp4[0] if mp4 else None)
        if pick:
            _dl(pick.replace("http://", "https://").replace(" ", "%20"), path)
            if os.path.getsize(path) > 200_000: return True
    return False

def _pexels(q, path):
    k = env("PEXELS_KEY")
    if not k: return False
    r = requests.get("https://api.pexels.com/videos/search", params={"query": q, "per_page": 5, "orientation": "landscape"}, headers={"Authorization": k}, timeout=30).json()
    for v in r.get("videos", []):
        files = sorted([f for f in v.get("video_files", []) if (f.get("width") or 0) >= 1280], key=lambda f: f.get("width") or 0)
        if files:
            _dl(files[0]["link"], path); return True
    return False

# ---------------- depth ----------------
_depth = None
def depth_map(img_path):
    """Depth-Anything-V2-Small (Apache-2.0). Falls back to a centre-weighted map."""
    global _depth
    im = Image.open(img_path).convert("RGB")
    if not FAKE and S("PARALLAX_ON", bool):
        try:
            if _depth is None:
                from transformers import pipeline
                _depth = pipeline("depth-estimation", model="depth-anything/Depth-Anything-V2-Small-hf", device=-1)
            d = np.asarray(_depth(im)["depth"].resize(im.size), dtype=np.float32)
            d = (d - d.min()) / (d.max() - d.min() + 1e-6); return d
        except Exception as e:
            log(f"depth model unavailable, using simple depth: {e}", "WARN"); _depth = False if _depth is None else _depth
    w, h = im.size; yy, xx = np.mgrid[0:h, 0:w]
    return (1 - np.sqrt(((xx - w / 2) / w) ** 2 + ((yy - h * 0.55) / h) ** 2) * 1.4).clip(0, 1).astype(np.float32)

# ---------------- motion graphics ----------------
def font(size, bold=True):
    for f in (["fonts/Anton-Regular.ttf"] if bold else []) + ["fonts/Inter-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]:
        if os.path.exists(f): return ImageFont.truetype(f, size)
    return ImageFont.load_default()

def _fmt(v, unit):
    a = abs(v)
    s = f"{v/1e9:.2f} billion" if a >= 1e9 else f"{v/1e6:.1f} million" if a >= 1e6 else f"{v:,.0f}"
    return (s + (" " + unit if unit else "")).strip()

def graphic_frame(g, t, W, H, bg=None):
    """Counter + gauge bar, eased. t in 0..1."""
    e = 1 - (1 - min(1, t * 1.25)) ** 3
    img = bg.copy() if bg is not None else Image.new("RGB", (W, H), (8, 12, 18))
    ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    d.rectangle([0, 0, W, H], fill=(0, 0, 0, 140))
    try: a, b = float(g.get("from", 0)), float(g.get("to", 100))
    except Exception: a, b = 0.0, 100.0
    v = a + (b - a) * e
    big = font(int(H * 0.16)); small = font(int(H * 0.045), bold=False)
    txt = _fmt(v, g.get("unit", ""))
    tw = d.textlength(txt, font=big); d.text(((W - tw) / 2, H * 0.34), txt, font=big, fill=(255, 255, 255, 255))
    lab = str(g.get("label", ""))[:48].upper(); lw = d.textlength(lab, font=small)
    d.text(((W - lw) / 2, H * 0.25), lab, font=small, fill=(120, 220, 255, 255))
    x0, x1, y = W * 0.2, W * 0.8, H * 0.62
    d.rectangle([x0, y, x1, y + H * 0.012], fill=(255, 255, 255, 60))
    d.rectangle([x0, y, x0 + (x1 - x0) * e, y + H * 0.012], fill=(120, 220, 255, 255))
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")
