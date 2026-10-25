"""whatifs/render.py v7.0 - segments (depth parallax stills, detail crops, clips, stock, graphics) piped straight into FFmpeg,
exact frame-accurate concat against the narration clock, procedural original score + SFX, ducking, loudness. Nothing written as PNG frames."""
from __future__ import annotations
import os, subprocess, json, math, random, hashlib
import numpy as np, cv2
from PIL import Image, ImageFilter
from whatifs.core import S, log, SMALL, WORK
from whatifs.media import depth_map, graphic_frame

FPS = 30
def out_size():
    if SMALL: return 640, 360
    h = S("OUTPUT_HEIGHT", int); return (2560, 1440) if h >= 1440 else (1920, 1080)
def work_size():
    return (640, 360) if SMALL else (1920, 1080)

def _enc_args(W, H, extra_vf=""):
    grade = "eq=contrast=1.06:saturation=1.08:gamma=0.98,vignette=PI/5,noise=alls=4:allf=t"
    vf = f"{extra_vf + ',' if extra_vf else ''}scale={W}:{H}:flags=lanczos,{grade},format=yuv420p"
    return ["-vf", vf, "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast" if not SMALL else "ultrafast",
            "-crf", "17", "-pix_fmt", "yuv420p", "-video_track_timescale", "15360", "-an"]

def _ease(t): return t * t * (3 - 2 * t)

def _pipe(path, frames_iter, nframes, ww, wh):
    W, H = out_size()
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{ww}x{wh}", "-r", str(FPS), "-i", "-"] + _enc_args(W, H) + ["-frames:v", str(nframes), path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = 0
    for fr in frames_iter:
        p.stdin.write(fr.tobytes()); n += 1
        if n >= nframes: break
    while n < nframes:   # safety: never short
        p.stdin.write(fr.tobytes()); n += 1
    p.stdin.close(); p.wait()
    if p.returncode: raise RuntimeError(f"ffmpeg pipe failed for {path}")
    return path

def _load(img_path, ww, wh, pad=1.3):
    im = cv2.imread(img_path)
    if im is None: raise RuntimeError(f"cannot read {img_path}")
    tw, th = int(ww * pad), int(wh * pad)
    s = max(tw / im.shape[1], th / im.shape[0]); im = cv2.resize(im, (int(im.shape[1] * s + 1), int(im.shape[0] * s + 1)), interpolation=cv2.INTER_LANCZOS4)
    y0, x0 = (im.shape[0] - th) // 2, (im.shape[1] - tw) // 2
    return im[y0:y0 + th, x0:x0 + tw]

def parallax_segment(img_path, path, nframes, seed, detail=False, depth=None):
    """Depth parallax camera move (wide) or a punched-in detail drift. Different move per shot, S-curve eased."""
    ww, wh = work_size(); rng = random.Random(seed)
    src = _load(img_path, ww, wh, 1.3 if not detail else 1.9)
    sh, sw = src.shape[:2]
    if depth is None: depth = depth_map(img_path)
    D = cv2.resize(depth, (sw, sh)).astype(np.float32)
    move = rng.choice(["push", "pull", "pan_l", "pan_r", "rise", "drift"])
    z0, z1 = {"push": (1.0, 1.16), "pull": (1.16, 1.0), "pan_l": (1.06, 1.1), "pan_r": (1.06, 1.1), "rise": (1.05, 1.12), "drift": (1.03, 1.09)}[move]
    dx = {"pan_l": 1, "pan_r": -1}.get(move, rng.uniform(-0.4, 0.4)) * sw * 0.05
    dy = {"rise": -1}.get(move, rng.uniform(-0.3, 0.3)) * sh * 0.04
    if detail:
        fy, fx = np.unravel_index(np.argmax(cv2.GaussianBlur(D, (0, 0), 25)), D.shape)
        cx0, cy0 = np.clip(fx, sw * 0.3, sw * 0.7), np.clip(fy, sh * 0.3, sh * 0.7)
    else: cx0, cy0 = sw / 2, sh / 2
    par = (0.0 if detail else sw * 0.018) * rng.choice([-1, 1])
    uu, vv = np.meshgrid(np.arange(ww, dtype=np.float32), np.arange(wh, dtype=np.float32))
    base_scale = ww / (sw / (1.3 if not detail else 1.9))
    def frames():
        for f in range(nframes):
            t = _ease(f / max(1, nframes - 1)); z = (z0 + (z1 - z0) * t) * base_scale
            cx, cy = cx0 + dx * (t - 0.5), cy0 + dy * (t - 0.5)
            mx = cx + (uu - ww / 2) / z; my = cy + (vv - wh / 2) / z
            if par:
                d = cv2.remap(D, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
                mx = mx + par * (t - 0.5) * (d - 0.5) * 2
            yield cv2.remap(src, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return _pipe(path, frames(), nframes, ww, wh)

def clip_segment(clip_path, path, nframes, loop=False):
    W, H = out_size(); ww, wh = work_size()
    dur_in = probe_dur(clip_path); want = nframes / FPS
    slow = 1.0 if loop else min(2.0, max(1.0, want / max(0.1, dur_in)))
    pre = f"scale={ww}:{wh}:force_original_aspect_ratio=increase,crop={ww}:{wh},setpts={slow:.4f}*PTS,fps={FPS},tpad=stop_mode=clone:stop_duration={want + 1:.2f}"
    cmd = ["ffmpeg", "-y", "-loglevel", "error"] + (["-stream_loop", "-1"] if loop else []) + ["-i", clip_path] + _enc_args(W, H, pre) + ["-frames:v", str(nframes), path]
    subprocess.run(cmd, check=True); return path

def graphic_segment(g, bg_path, path, nframes):
    ww, wh = work_size()
    bg = None
    if bg_path and os.path.exists(bg_path):
        bg = Image.open(bg_path).convert("RGB").resize((ww, wh)).filter(ImageFilter.GaussianBlur(14))
    def frames():
        for f in range(nframes):
            im = graphic_frame(g, f / max(1, nframes - 1), ww, wh, bg)
            yield cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)
    return _pipe(path, frames(), nframes, ww, wh)

def probe_dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p], capture_output=True, text=True)
    try: return float(r.stdout.strip())
    except Exception: return 0.0

def concat(segs, path):
    lst = path + ".txt"
    with open(lst, "w") as f:
        for s in segs: f.write(f"file '{os.path.abspath(s)}'\n")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", path], check=True)
    return path

# ---------------- original score + SFX (no licensing risk) ----------------
SR = 48000
def score(duration, seed, events, voice_wav=None, bed_db=-24, duck_db=9):
    rng = np.random.default_rng(int(hashlib.md5(seed.encode()).hexdigest()[:8], 16)); n = int(duration * SR)
    t = np.arange(n, dtype=np.float32) / SR
    root = float(rng.choice([41.2, 43.65, 46.25, 49.0, 55.0]))
    chord = [root, root * 1.5, root * 2, root * 2.4 if rng.random() < .5 else root * 2.25, root * 3]
    L = np.zeros(n, np.float32); Rr = np.zeros(n, np.float32)
    for i, f in enumerate(chord):
        lfo = 0.6 + 0.4 * np.sin(2 * np.pi * (0.013 + 0.007 * i) * t + rng.uniform(0, 6.28)).astype(np.float32)
        ph = rng.uniform(0, 6.28); amp = 0.22 / (1 + i * 0.6)
        L += (amp * lfo * np.sin(2 * np.pi * f * 0.999 * t + ph)).astype(np.float32)
        Rr += (amp * lfo * np.sin(2 * np.pi * f * 1.001 * t + ph + 0.4)).astype(np.float32)
    for ch in (L, Rr):
        noise = rng.standard_normal(n).astype(np.float32)
        noise = cv2.GaussianBlur(noise.reshape(1, -1), (0, 0), sigmaX=40).ravel() * 6
        ch += noise * 0.05
    bed = np.stack([L, Rr], 1); bed /= (np.abs(bed).max() + 1e-6); bed *= 10 ** (bed_db / 20)
    sfx = np.zeros(n, np.float32)
    for kind, at in events:
        i0 = int(at * SR)
        if i0 >= n: continue
        if kind == "boom":
            m = int(2.2 * SR); tt = np.arange(m) / SR
            s = (np.sin(2 * np.pi * (52 * np.exp(-tt * 1.4) + 28) * tt) * np.exp(-tt * 2.2)).astype(np.float32) * 0.5
        elif kind == "whoosh":
            m = int(0.7 * SR); x = rng.standard_normal(m).astype(np.float32)
            x = cv2.GaussianBlur(x.reshape(1, -1), (0, 0), sigmaX=3).ravel() * 3
            s = x * np.sin(np.linspace(0, np.pi, m)).astype(np.float32) ** 2 * 0.12
        elif kind == "riser":
            m = int(3.0 * SR); tt = np.arange(m) / SR
            s = (np.sin(2 * np.pi * (200 + 600 * tt / 3) * tt) * (tt / 3) ** 2).astype(np.float32) * 0.05
            i0 = max(0, i0 - m)
        else: continue
        e = min(n, i0 + len(s)); sfx[i0:e] += s[: e - i0]
    mix = bed.copy()
    if voice_wav is not None:
        import soundfile as sf
        v, vsr = sf.read(voice_wav, dtype="float32")
        if v.ndim > 1: v = v.mean(1)
        if vsr != SR: v = cv2.resize(v.reshape(1, -1), (int(len(v) * SR / vsr), 1)).ravel()
        v = np.pad(v, (0, max(0, n - len(v))))[:n]
        env = np.abs(v); env = cv2.GaussianBlur(env.reshape(1, -1), (0, 0), sigmaX=SR * 0.12).ravel()
        g = 1 - (1 - 10 ** (-duck_db / 20)) * np.clip(env / (env.max() * 0.15 + 1e-6), 0, 1)
        mix *= g[:, None]
        mix += v[:, None]
    mix += sfx[:, None]
    return mix

def write_mix(mix, path, lufs=-14):
    import soundfile as sf
    raw = path + ".raw.wav"; sf.write(raw, np.clip(mix, -1, 1), SR, subtype="PCM_24")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-af", f"loudnorm=I={lufs}:TP=-1.0:LRA=11,aresample={SR}", "-ar", str(SR), path], check=True)
    os.remove(raw); return path

def mux(video, audio, path):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video, "-i", audio, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "320k", "-ar", "48000", "-shortest", "-movflags", "+faststart", path], check=True)
    return path

# ---------------- captions ----------------
def _ts(t, comma=True):
    h, m = int(t // 3600), int(t % 3600 // 60); s = t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", "," if comma else ".")
def srt(timeline, path, max_words=7):
    out, k = [], 1
    for u in timeline["units"]:
        ws = u.get("words") or []
        if not ws:
            ws = [{"w": x, "s": u["start"] + i * (u["end"] - u["start"]) / max(1, len(u["text"].split())), "e": 0} for i, x in enumerate(u["text"].split())]
            for i in range(len(ws)): ws[i]["e"] = ws[i + 1]["s"] if i + 1 < len(ws) else u["end"]
        for i in range(0, len(ws), max_words):
            g = ws[i:i + max_words]
            out.append(f"{k}\n{_ts(g[0]['s'])} --> {_ts(g[-1]['e'])}\n{' '.join(x['w'] for x in g)}\n"); k += 1
    open(path, "w").write("\n".join(out)); return path
