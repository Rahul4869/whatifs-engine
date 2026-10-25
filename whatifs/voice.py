"""
whatifs/voice.py  v6.1.0
Original blended narrator voice + human-style pacing.

- Voice: weighted mix of 2-3 Kokoro-82M (Apache-2.0) voice embeddings -> a new voice owned by nobody.
- Pacing: per-sentence speed drift, meaning-based pauses, comic beats, soft breaths, room tone.
- Output: narration WAV (48 kHz mono, -16 LUFS) + timeline JSON (sentence + word timings)
  which is the MASTER CLOCK for every visual (Kernel K14).
No watermark/detection tampering of any kind (Kernel K30).
"""
from __future__ import annotations
import hashlib, json, math, os, re, subprocess, random
from dataclasses import dataclass, field, asdict
import numpy as np

SR = 24000            # Kokoro native rate
OUT_SR = 48000

# ---------- pacing styles (rotated + learned later; values are starting points) ----------
STYLES = {
    #               base speed, gap multiplier, speed jitter, arc (start->end multiplier)
    "hypnotic":       dict(base=0.93, gap=1.25, jit=0.020, arc=(1.00, 1.00)),
    "urgent":         dict(base=1.05, gap=0.80, jit=0.030, arc=(1.00, 1.00)),
    "slow_burn":      dict(base=0.97, gap=1.05, jit=0.025, arc=(0.96, 1.05)),
    "brake":          dict(base=1.00, gap=0.95, jit=0.025, arc=(1.05, 0.94)),
    "conversational": dict(base=1.00, gap=1.00, jit=0.035, arc=(1.00, 1.00)),
}
TAGS = {  # speed multiplier, extra gap before (s), extra gap after (s)
    "calm":    (0.96, 0.00, 0.10),
    "tension": (1.05, 0.00, 0.00),
    "reveal":  (0.91, 0.40, 0.35),
    "aside":   (1.02, 0.20, 0.45),   # humour: land the line, then let it sit
    "callback":(0.98, 0.30, 0.60),
    "none":    (1.00, 0.00, 0.00),
}

@dataclass
class Blend:
    name: str
    parts: dict            # {"af_heart":0.5, ...}
    lang: str = "a"        # American English pronunciation
    def voiceprint(self) -> str:
        key = json.dumps({"p": dict(sorted(self.parts.items())), "l": self.lang}, sort_keys=True)
        return "WI-VOICE-" + hashlib.sha256(key.encode()).hexdigest()[:10].upper()

@dataclass
class Unit:
    text: str
    tag: str = "none"
    gap_before: float = 0.0
    hesitate_after: float = 0.0     # from "..." or [beat]
    new_para: bool = False

# ---------- script parsing ----------
_TAG_RE = re.compile(r"^\[(\w+)(?::(\w+))?\]\s*")
def parse_script(script: str) -> list[Unit]:
    """Lines may start with [calm] [tension] [reveal] [aside] [callback] [pause:long] [pause:short].
    Inline: '...' = hesitation, [beat] = comic micro-pause."""
    units: list[Unit] = []
    pending_gap = 0.0; para = False
    for raw in script.splitlines():
        line = raw.strip()
        if not line:
            para = True; continue
        tag = "none"
        m = _TAG_RE.match(line)
        if m:
            t, arg = m.group(1).lower(), (m.group(2) or "").lower()
            line = line[m.end():].strip()
            if t == "pause":
                pending_gap += {"long": 1.6, "short": 0.6}.get(arg, 1.0); continue
            tag = t if t in TAGS else "none"
        if not line: continue
        sentences = re.split(r"(?<=[.!?])\s+", line)
        for i, s in enumerate(sentences):
            pieces = re.split(r"\s*(?:\.\.\.|…|\[beat\])\s*", s)
            for j, p in enumerate(pieces):
                p = p.strip()
                if not p: continue
                u = Unit(text=p, tag=tag, gap_before=pending_gap, new_para=para and i == 0 and j == 0)
                if j < len(pieces) - 1: u.hesitate_after = 1.0
                units.append(u); pending_gap = 0.0; para = False
    return units

# ---------- audio helpers ----------
def _trim(a: np.ndarray, thr_db=-45.0, keep=0.03) -> np.ndarray:
    if a.size == 0: return a
    win = int(0.01 * SR)
    env = np.sqrt(np.convolve(a.astype(np.float64)**2, np.ones(win)/win, mode="same"))
    idx = np.where(env > 10 ** (thr_db / 20))[0]
    if idx.size == 0: return a
    s = max(0, idx[0] - int(keep*SR)); e = min(a.size, idx[-1] + int(keep*SR))
    return a[s:e]

def _breath(rng: random.Random, db: float = -34.0) -> np.ndarray:
    """Soft synthetic inhale: band-limited noise with a rise/fall envelope, ~-40 dBFS."""
    n = int(rng.uniform(0.20, 0.34) * SR)
    nr = np.random.default_rng(rng.randrange(1 << 30))
    x = nr.standard_normal(n)
    X = np.fft.rfft(x); f = np.fft.rfftfreq(n, 1/SR)
    X *= ((f > 400) & (f < 3200)) * (1 / np.maximum(f, 1) ** 0.3)
    x = np.fft.irfft(X, n)
    t = np.linspace(0, 1, n); env = np.sin(np.pi * t) ** 1.6
    x = x * env; x /= (np.sqrt(np.mean(x**2)) + 1e-9)
    return (x * 10 ** (db / 20)).astype(np.float32)

def _sil(sec: float) -> np.ndarray: return np.zeros(int(max(0, sec) * SR), dtype=np.float32)

# ---------- TTS backend ----------
class KokoroBackend:
    def __init__(self, blend: Blend):
        import torch
        from kokoro import KPipeline
        self.torch = torch
        self.pipe = KPipeline(lang_code=blend.lang)
        total = sum(blend.parts.values())
        pack = None
        for name, wgt in blend.parts.items():
            loader = getattr(self.pipe, "load_single_voice", None) or self.pipe.load_voice
            v = loader(name).float()
            pack = v * (wgt / total) if pack is None else pack + v * (wgt / total)
        self.pack = pack
    def synth(self, text: str, speed: float):
        audio, words, off = [], [], 0.0
        for r in self.pipe(text, voice=self.pack, speed=speed):
            a = r.audio.detach().cpu().numpy() if hasattr(r.audio, "detach") else np.asarray(r.audio)
            for tk in (getattr(r, "tokens", None) or []):
                st, en = getattr(tk, "start_ts", None), getattr(tk, "end_ts", None)
                if st is not None and en is not None and tk.text.strip():
                    words.append({"w": tk.text, "s": off + float(st), "e": off + float(en)})
            audio.append(a.astype(np.float32)); off += a.size / SR
        return (np.concatenate(audio) if audio else np.zeros(0, np.float32)), words

# ---------- the narrator ----------
@dataclass
class NarrationResult:
    wav_path: str
    timeline_path: str
    duration: float
    voiceprint: str
    style: str

def narrate(script: str, blend: Blend, out_base: str, style: str = "slow_burn",
            seed: str = "lab", humanize: bool = True, breaths: bool = True,
            backend=None) -> NarrationResult:
    rng = random.Random(hashlib.md5(f"{seed}|{style}".encode()).hexdigest())
    try:
        from whatifs.core import S
        trim, bdb, brate = S("SPEED_TRIM", float), S("BREATH_DB", float), S("BREATH_RATE", float)
    except Exception:
        trim, bdb, brate = 1.04, -34.0, 0.6
    st = dict(STYLES.get(style, STYLES["slow_burn"])); st["base"] *= trim; be = backend or KokoroBackend(blend)
    units = parse_script(script); n = max(1, len(units))
    chunks, timeline, t = [], [], 0.0
    def add(a):
        nonlocal t
        chunks.append(a); t += a.size / SR
    add(_sil(0.35))
    for i, u in enumerate(units):
        sm, gb, ga = TAGS.get(u.tag, TAGS["none"])
        if humanize:
            prog = i / max(1, n - 1)
            arc = st["arc"][0] + (st["arc"][1] - st["arc"][0]) * prog
            speed = st["base"] * arc * sm * (1 + rng.gauss(0, st["jit"]))
            speed = min(1.15, max(0.85, speed))
            gap = (rng.gauss(0.38, 0.07) if i else 0.0) * st["gap"]
            if u.new_para: gap += rng.uniform(0.30, 0.55)
            gap = max(0.0, gap) + gb + u.gap_before
            if i and humanize and breaths and gap >= 0.40 and len(u.text.split()) >= 7 and rng.random() < brate:
                b = _breath(rng, bdb); pre = max(0.05, gap - b.size / SR - 0.08)
                add(_sil(pre)); add(b); add(_sil(0.08))
            else:
                add(_sil(gap))
        else:
            speed = 1.0; add(_sil((0.25 if i else 0) + u.gap_before))
        audio, words = be.synth(u.text, speed)
        audio = _trim(audio)
        start = t; add(audio)
        timeline.append({"i": i, "text": u.text, "tag": u.tag, "speed": round(speed, 3),
                         "start": round(start, 3), "end": round(t, 3),
                         "words": [{"w": x["w"], "s": round(start + x["s"], 3), "e": round(start + x["e"], 3)} for x in words]})
        if humanize:
            tail = ga + (rng.uniform(0.35, 0.60) if u.hesitate_after else 0.0)
            if tail: add(_sil(tail))
    add(_sil(0.6))
    raw = np.concatenate(chunks)
    raw_path = out_base + "_raw.wav"
    _write_wav(raw_path, raw, SR)
    wav_path = out_base + ".wav"
    _master(raw_path, wav_path)
    os.remove(raw_path)
    dur = _probe(wav_path)
    tl = {"voiceprint": blend.voiceprint(), "blend": blend.parts, "style": style,
          "humanized": humanize, "duration": dur, "units": timeline}
    tl_path = out_base + "_timeline.json"
    json.dump(tl, open(tl_path, "w"), indent=1)
    return NarrationResult(wav_path, tl_path, dur, blend.voiceprint(), style)

def _write_wav(path, a, sr):
    import soundfile as sf
    sf.write(path, np.clip(a, -1, 1), sr, subtype="PCM_16")

def _master(src, dst):
    """Gentle broadcast chain: rumble cut, warmth, light compression, tiny room, room tone, loudness."""
    af = ("highpass=f=70,equalizer=f=180:t=q:w=1.2:g=1.5,equalizer=f=3500:t=q:w=1.5:g=1.0,"
          "acompressor=threshold=-20dB:ratio=2.5:attack=15:release=200,"
          "aecho=0.85:0.4:17|31:0.05|0.03,aresample=48000")
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", src,
           "-f", "lavfi", "-i", "anoisesrc=color=pink:amplitude=0.0009:sample_rate=48000",
           "-filter_complex", f"[0:a]{af}[v];[v][1:a]amix=inputs=2:duration=first:normalize=0,"
           "loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[o]",
           "-map", "[o]", "-ac", "1", "-ar", str(OUT_SR), dst]
    subprocess.run(cmd, check=True)

def _probe(p) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                       capture_output=True, text=True, check=True)
    return round(float(r.stdout.strip()), 3)
