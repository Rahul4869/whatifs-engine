"""whatifs/qc.py v7.0 - quality checks before anything goes public. Any FAIL stops upload of that file (fail-safe, logged)."""
from __future__ import annotations
import subprocess, re, json
from whatifs.render import probe_dur

def _ff(args):
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostats"] + args + ["-f", "null", "-"], capture_output=True, text=True).stderr

def check_video(path, expect_sec, tol=1.5, vertical=False):
    res = {}
    d = probe_dur(path); res["duration"] = (abs(d - expect_sec) <= tol, round(d, 2))
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,r_frame_rate,sample_rate", "-of", "json", path], capture_output=True, text=True)
    st = json.loads(p.stdout or "{}").get("streams", [])
    v = next((s for s in st if s["codec_type"] == "video"), {}); a = next((s for s in st if s["codec_type"] == "audio"), {})
    res["has_audio"] = (bool(a), a.get("sample_rate")); res["has_video"] = (bool(v), f'{v.get("width")}x{v.get("height")}')
    res["orientation"] = ((v.get("height", 0) > v.get("width", 0)) == vertical, "")
    e = _ff(["-i", path, "-af", "ebur128", "-vn"])
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", e); lufs = float(m[-1]) if m else -99
    res["loudness"] = (-17.5 <= lufs <= -11.5, lufs)
    e = _ff(["-i", path, "-vf", "blackdetect=d=2.5:pix_th=0.06", "-an"])
    blacks = re.findall(r"black_duration:([\d.]+)", e); res["no_long_black"] = (not blacks, blacks[:3])
    e = _ff(["-i", path, "-af", "silencedetect=n=-50dB:d=4", "-vn"])
    sil = re.findall(r"silence_duration: ([\d.]+)", e); res["no_long_silence"] = (not sil, sil[:3])
    e = _ff(["-i", path, "-vf", "freezedetect=n=0.001:d=9", "-an"])
    fr = re.findall(r"freeze_duration: ([\d.]+)", e); res["no_frozen_picture"] = (not fr, fr[:3])
    ok = all(v[0] for v in res.values())
    return ok, res

def check_thumb(path, phone_score):
    import os
    ok = os.path.exists(path) and os.path.getsize(path) < 2_000_000 and phone_score > 38
    return ok, {"size": os.path.getsize(path) if os.path.exists(path) else 0, "phone_contrast": round(phone_score, 1)}
