"""whatifs/reels.py v7.0 - 9:16 reels from the long video's own shots: cover frame first, new order, re-voiced lines,
burned captions, cut-to-black on the question, end card. 1080x1920."""
from __future__ import annotations
import os, subprocess
from whatifs.core import log, SMALL
from whatifs.voice import narrate
from whatifs.render import probe_dur, srt, score, write_mix

def _vsize(): return (360, 640) if SMALL else (1080, 1920)

def _ass(timeline, path, hook_text, W, H):
    fs = int(H * 0.042); hs = int(H * 0.05)
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Anton,{fs},&H00FFFFFF,&H0000D7FF,&H00000000,&H64000000,1,0,0,0,100,100,1,0,1,{max(2,fs//9)},2,2,60,60,{int(H*0.30)},1
Style: Hook,Anton,{hs},&H0000D7FF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,1,0,1,{max(3,hs//8)},3,8,60,60,{int(H*0.12)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    def ts(t): h, m = int(t // 3600), int(t % 3600 // 60); s = t % 60; return f"{h}:{m:02d}:{s:05.2f}"
    ev = [f"Dialogue: 1,{ts(0)},{ts(2.6)},Hook,,0,0,0,,{hook_text.upper()}"]
    for u in timeline["units"]:
        ws = u.get("words") or []
        if not ws:
            parts = u["text"].split(); d = (u["end"] - u["start"]) / max(1, len(parts))
            ws = [{"w": p, "s": u["start"] + i * d, "e": u["start"] + (i + 1) * d} for i, p in enumerate(parts)]
        for i in range(0, len(ws), 3):
            g = ws[i:i + 3]
            ev.append(f"Dialogue: 0,{ts(g[0]['s'])},{ts(g[-1]['e'])},Cap,,0,0,0,,{' '.join(x['w'] for x in g).upper()}")
    open(path, "w").write(head + "\n".join(ev) + "\n"); return path

def build_reel(k, plan, shot_files, cover, blend, style, out_dir, fonts_dir="fonts"):
    W, H = _vsize(); os.makedirs(out_dir, exist_ok=True)
    lines = "\n".join(plan["lines"] + ["[pause:short]", "[reveal] " + plan.get("end_line", "Full video on our channel.")])
    vo = narrate(lines, blend, os.path.join(out_dir, f"reel{k}_vo"), style=style, seed=f"reel{k}")
    import json
    tl = json.load(open(vo.timeline_path)); dur = vo.duration + 0.4
    segs = []; per = max(1.6, (dur - 0.8) / max(1, len(plan["shots"])))
    vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps=30,format=yuv420p"
    c0 = os.path.join(out_dir, f"r{k}_c.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", cover, "-t", "0.8", "-vf",
                    f"scale={W*1.08:.0f}:-2,zoompan=z='1+0.0015*on':d=1:s={W}x{H}:fps=30,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-video_track_timescale", "15360", c0], check=True)
    segs.append(c0)
    for j, i in enumerate(plan["shots"]):
        src = shot_files[i]; o = os.path.join(out_dir, f"r{k}_{j}.mp4")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-t", f"{per:.2f}", "-vf", vf + ",tpad=stop_mode=clone:stop_duration=3", "-t", f"{per:.2f}",
                        "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-video_track_timescale", "15360", o], check=True)
        segs.append(o)
    lst = os.path.join(out_dir, f"r{k}.txt"); open(lst, "w").write("".join(f"file '{os.path.abspath(s)}'\n" for s in segs))
    body = os.path.join(out_dir, f"r{k}_body.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", body], check=True)
    ass = _ass(tl, os.path.join(out_dir, f"r{k}.ass"), plan.get("hook_text", ""), W, H)
    mix = score(dur, f"reel{k}", [("riser", max(0.5, dur - 1.6)), ("boom", 0.05)], vo.wav_path, bed_db=-20)
    aud = write_mix(mix, os.path.join(out_dir, f"r{k}_mix.wav"), lufs=-13)
    out = os.path.join(out_dir, f"reel{k}.mp4")
    fd = os.path.abspath(fonts_dir) if os.path.isdir(fonts_dir) else "/usr/share/fonts"
    end_fade = f"fade=t=out:st={max(0.1, dur - 0.35):.2f}:d=0.35"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", body, "-i", aud, "-filter_complex",
                    f"[0:v]tpad=stop_mode=clone:stop_duration=5,trim=duration={dur:.2f},ass={ass}:fontsdir={fd},{end_fade}[v]",
                    "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "256k",
                    "-t", f"{dur:.2f}", "-movflags", "+faststart", out], check=True)
    return out, dur
