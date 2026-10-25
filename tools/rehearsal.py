"""tools/rehearsal.py v7.0 - full offline run: setup -> voices -> tick -> produce -> release x2 -> trends -> learn -> brief.
Fake models, fake images, synthetic voice. Proves every stage connects. Costs nothing. Used by CI and the repair bot."""
import os, json, shutil, datetime as dt
import numpy as np

class ToneVoice:
    SR = 24000
    def synth(self, text, speed):
        n = int(max(0.4, len(text) * 0.058 / speed) * self.SR); t = np.arange(n) / self.SR
        a = (0.25 * np.sin(2 * np.pi * 150 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 3.3 * t))).astype(np.float32)
        a = np.concatenate([np.zeros(1800, np.float32), a, np.zeros(2400, np.float32)])
        ws = text.split(); d = (n / self.SR) / max(1, len(ws))
        return a, [{"w": x, "s": 0.075 + i * d, "e": 0.075 + (i + 1) * d} for i, x in enumerate(ws)]

def run():
    assert os.environ.get("WI_FAKE") == "1", "rehearsal needs WI_FAKE=1"
    work = os.environ.get("WI_WORK", "rh"); shutil.rmtree(work, ignore_errors=True); os.makedirs(work, exist_ok=True)
    import whatifs.voice as V
    real = V.KokoroBackend
    V.KokoroBackend = lambda blend: ToneVoice()
    try:
        from whatifs.core import store, set_setting, now_utc, flush_costs
        def st_rows(t): flush_costs(); return store().rows(t)
        from whatifs import manage as MG, episode as EP
        from whatifs.voice_lab import main as voices
        MG.setup(); print("setup ok")
        voices(backend=ToneVoice()); print("voices ok")
        a = MG.tick()["action"]; assert a == "waiting_for_voice_pick", a          # v7.2: nothing is made before the voice pick
        set_setting("VOICE", "C")
        a = MG.tick()["action"]; assert a in ("idle", "produce"), a
        slot = (now_utc() + dt.timedelta(hours=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        r = EP.produce(slot); print("produce ok", json.dumps(r, default=str)[:400])
        assert os.path.exists(r["master"]) and len(r["reels"]) >= 1, "missing outputs"
        # v7.2 independent checks on the real rendered files
        from whatifs import qc as QC
        from whatifs.render import probe_dur
        ok, info = QC.check_video(r["master"], probe_dur(r["master"])); assert ok, info
        for rf in r["reels"]:
            ok, info = QC.check_video(rf, probe_dur(rf), vertical=True); assert ok, (rf, info)
        assert probe_dur(r["master"]) >= 20, "runtime floor not enforced"
        imgs = [c for c in st_rows("Cost_Log") if c["item"] == "image"]
        print("rehearsal images logged:", len(imgs))
        st = store(); e = st.rows("Episodes")[-1]; assert e["status"] == "SCHEDULED", e
        past = (now_utc() - dt.timedelta(hours=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
        st.update("Episodes", "episode_id", e["episode_id"], {"slot_et": past})
        a = MG.tick(); assert a["action"] == "release1", a; MG.release(e["episode_id"], "release1")
        a = MG.tick(); assert a["action"] == "release2", a; MG.release(e["episode_id"], "release2")
        assert st.rows("Episodes")[-1]["status"] == "LIVE"
        MG.trend_scout(); print("trends ok")
        old = (now_utc() - dt.timedelta(days=4)).strftime("%Y-%m-%dT%H:%M:%SZ")
        st.update("Episodes", "episode_id", e["episode_id"], {"slot_et": old})
        MG.learn(); assert st.rows("Analytics"), "no analytics"; print("learn ok")
        MG.money_check(); MG.monthly_brief(); print("brief ok")
        print("REHEARSAL: GREEN")
    finally:
        V.KokoroBackend = real
