"""whatifs/voice_lab.py v7.0 - 4 original voices + 1 flat comparison. Samples are emailed + uploaded to Drive + kept as a GitHub artifact."""
import os, subprocess, json
from whatifs.voice import Blend, narrate
from whatifs.episode import BLENDS
from whatifs.core import set_setting, iso, S, FAKE

DEMO = """[calm] Right now, about eight billion people have fingernails. And every week... we cut a little bit off.
[tension] So picture this. At exactly noon, everyone on Earth drops their clippings into the ocean. At once.
[pause:long]
[reveal] That's roughly two hundred tonnes of keratin, hitting the water in the same second.
[aside] And the ocean does... [beat] absolutely nothing. Which, if you've ever sent a long heartfelt text and got back "k", is a feeling you already know.
[tension] But two hundred tonnes doesn't just vanish. It sinks. And down there, something is waiting for it.
"""

def main(backend=None):
    out = "voice_samples"; os.makedirs(out, exist_ok=True); links = []
    def mp3(wav):
        m = wav[:-4] + ".mp3"; subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-b:a", "192k", m], check=True); os.remove(wav); return m
    for k, parts in BLENDS.items():
        r = narrate(DEMO, Blend(k, parts), f"{out}/voice_{k}", style="slow_burn", seed="lab", backend=backend); links.append((k, mp3(r.wav_path), r.voiceprint))
    r = narrate(DEMO, Blend("C", BLENDS["C"]), f"{out}/voice_E_no_pacing", humanize=False, seed="lab", backend=backend); links.append(("E", mp3(r.wav_path), "flat"))
    set_setting("VOICE_SAMPLES_AT", iso())
    if not FAKE:
        from whatifs import publish as PUB
        html = ["<p>Listen on your phone with earphones. Then open the Sheet, Settings tab, and type A, B, C or D in the VOICE cell (or A+C to mix two).</p><ul>"]
        for k, path, vp in links:
            try: _, url = PUB.drive_upload(path, os.path.basename(path), public=True); html.append(f"<li><a href='{url}'>Voice {k}</a> ({vp})</li>")
            except Exception as e: html.append(f"<li>Voice {k}: see GitHub artifact ({e})</li>")
        html.append("</ul><p>E is voice C with the human pacing switched off, for comparison. If you don't choose within 72 hours, A is used.</p>")
        PUB.email("Pick your narrator voice", "".join(html))
    return links

if __name__ == "__main__":
    main()
