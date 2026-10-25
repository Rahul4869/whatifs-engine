"""whatifs/episode.py v7.0 - one full episode: plan -> voice (master clock) -> shots -> assets -> render -> art -> reels -> QC -> schedule.
Long video is uploaded PRIVATE with publishAt = slot. Reels go out 15 min and 6 h after it is live (separate 'release' job).
Every expensive step happens only after free checks pass. Missing assets degrade to free alternatives; nothing blocks."""
from __future__ import annotations
import os, json, re, random, datetime as dt, concurrent.futures as cf
from whatifs.core import S, log, store, iso, JOB, WORK, FAKE, SMALL, flush_log, now_utc, set_setting
from whatifs import room as ROOM, media as M, render as RN, art as ART, reels as REELS, qc as QC, publish as PUB
from whatifs.voice import narrate, Blend
from whatifs.sampler import draw as DRAW
from whatifs.governor import plan_for_episode, fal_allowed, episodes_left_this_month

BLENDS = {
    "A": {"am_michael": 0.50, "am_fenrir": 0.30, "am_puck": 0.20},
    "B": {"am_michael": 0.55, "bm_george": 0.25, "am_onyx": 0.20},
    "C": {"af_heart": 0.50, "af_bella": 0.30, "af_nicole": 0.20},
    "D": {"af_heart": 0.40, "af_kore": 0.35, "af_aoede": 0.25},
}
def blend():
    v = (S("VOICE") or "A").strip().upper()
    if "+" in v:  # e.g. "A+C" = 50/50 mix of two recipes
        parts = {}
        for k in v.split("+"):
            for n, wgt in BLENDS.get(k.strip(), BLENDS["A"]).items(): parts[n] = parts.get(n, 0) + wgt / 2
        return Blend("custom", parts)
    return Blend(v, BLENDS.get(v, BLENDS["A"]))

def est_cost_inr(d):
    u = S("USD_INR", float)
    return u * (d["stills"] * S("PRICE_STILL_USD", float) + 3 * S("PRICE_THUMB_USD", float) + d["living"] * S("PRICE_LIVING_USD", float)
                + d["kling"] * S("PRICE_KLING_USD", float)) + 70

def chapters(timeline, beats_at):
    ch = [("0:00", "Intro")]
    for i, (t, name) in enumerate(beats_at):
        if t < 10 or t - _sec(ch[-1][0]) < 45: continue
        ch.append((f"{int(t//60)}:{int(t%60):02d}", name[:40]))
    return ch if len(ch) >= 3 else ch[:1]
def _sec(s): m, x = s.split(":"); return int(m) * 60 + int(x)

def produce(slot_iso, episode_id=None, eps_left=None):
    ep = episode_id or ("EP" + now_utc().strftime("%Y%m%d%H%M"))
    JOB["episode"] = ep; out = os.path.join(WORK, ep); os.makedirs(out, exist_ok=True)
    st = store()
    st.append("Episodes", [{"episode_id": ep, "slot_et": slot_iso, "status": "PLANNING", "updated": iso()}])
    try:
        # 1. plan (Claude room + Gemini critic)
        if not fal_allowed():
            raise RuntimeError("image credit is empty - top up fal.ai (reminder email sent); will retry next hour")
        eps_left = eps_left or episodes_left_this_month()
        d = DRAW(ep, "collective")
        plan = plan_for_episode(est_cost_inr(d), eps_left); d["kling"], d["living"] = plan["kling"], plan["living"]
        log(f"draw: {json.dumps(d)} | spend plan: {plan['reason']}")
        room = ROOM.run_room(d, ep)
        d["ptype"] = room["spine"].get("ptype", d["ptype"])
        if room["spine"].get("family"): d["strategies"]["family"] = room["spine"]["family"]; d["family"] = room["spine"]["family"]
        st.update("Episodes", "episode_id", ep, {"premise": room["spine"]["premise"], "ptype": d["ptype"], "status": "VOICING", "draw_json": d})
        _mark_premise(room["spine"]["premise"], ep)
        # 2. voice = master clock
        script = room["script"]["script"]
        beat_names = [b.get("purpose", f"Part {b.get('n')}") for b in room["bible"].get("beats", [])]
        clean, beat_marks = _strip_beats(script)
        vo = narrate(clean, blend(), os.path.join(out, "voice"), style=d["strategies"]["voice"] or "slow_burn", seed=ep)
        floor = 20 if SMALL else S("RUNTIME_MIN_SEC", int) + 3
        for attempt in range(2):
            if vo.duration >= floor: break
            short = floor - vo.duration; add_words = int(short / 60 * S("WPM_ESTIMATE", float) * 1.25) + 40
            log(f"narration {vo.duration:.0f}s is under {floor}s - asking the writer for ~{add_words} more words (free step)", "WARN")
            longer = ROOM.extend(room, script, add_words, ep)
            if longer: script = longer; clean, beat_marks = _strip_beats(script)
            vo = narrate(clean, blend(), os.path.join(out, "voice"), style=d["strategies"]["voice"] or "slow_burn", seed=ep)
        if vo.duration < floor:
            raise RuntimeError(f"narration {vo.duration:.0f}s still under {floor}s - not spending on visuals; will retry")
        room["script"]["script"] = script
        tl = json.load(open(vo.timeline_path)); units = tl["units"]
        log(f"narration {vo.duration:.1f}s, {len(units)} units, voice {vo.voiceprint}")
        # 3. shot list (free) + continuity check (free) before any image money
        shots = ROOM.plan_shots(room, units, d, plan, ep)
        sync = ROOM.continuity({"script": clean[:20000], "shots": shots[:80], "spine": room["spine"]}, ep)
        if not sync.get("ok", True) and sync.get("problems"):
            log(f"continuity problems: {sync['problems'][:5]} - re-planning shots once", "WARN")
            room["bible"]["look"] = room["bible"].get("look", "") + " | fix: " + "; ".join(p.get("fix", "") for p in sync["problems"][:5])
            shots = ROOM.plan_shots(room, units, d, plan, ep)
        st.update("Episodes", "episode_id", ep, {"status": "VISUALS"})
        # 4. assets
        files = _assets(shots, units, out, ep, budget=d["stills"] + plan["living"] + plan["kling"])
        need_img = files["anchors"]
        miss = [i for i in need_img if i not in files["img"]]
        log(f"images: {len(files['img'])} new for {len(shots)} shots (cap {d['stills'] + plan['living'] + plan['kling']})")
        if need_img and len(miss) / len(need_img) > 0.15:
            raise RuntimeError(f"{len(miss)} of {len(need_img)} images failed - not publishing a weak video; will retry")
        # 5. render long video against the narration clock
        master = _render(files, shots, units, vo, out, ep)
        # 6. packaging + art
        beats_at = [(units[i]["start"], beat_names[k] if k < len(beat_names) else f"Part {k+1}") for k, i in enumerate(beat_marks) if i < len(units)]
        chs = chapters(tl, beats_at)
        pkg = ROOM.package(room, chs, d, ep)
        thumb, thumb_master, phone = ART.thumbnail(pkg.get("thumb_prompt", room["spine"]["premise"]), pkg.get("thumb_text", ""), out, ep)
        okt, tinfo = QC.check_thumb(thumb, phone)
        if not okt:
            log(f"thumbnail weak {tinfo}, retrying with a different seed", "WARN")
            thumb, thumb_master, phone = ART.thumbnail(pkg.get("thumb_prompt", "") + ", higher contrast, brighter subject", pkg.get("thumb_text", ""), out, ep + "b")
        covers = [ART.reel_cover(p, t, out, ep, k) for k, (p, t) in enumerate(zip((pkg.get("reel_cover_prompts") or ["", ""])[:2], (pkg.get("reel_cover_texts") or ["", ""])[:2]))]
        # 7. reels
        rplans = ROOM.reels(room, shots, d, ep)
        reel_files = []
        for k, rp in enumerate(rplans[:2]):
            try:
                cov = covers[k] if k < len(covers) else thumb_master
                rf, rd = REELS.build_reel(k, rp, files["segments"], cov, blend(), "urgent", out)
                ok, info = QC.check_video(rf, rd, vertical=True, tol=1.0)
                if ok: reel_files.append((rf, rp, cov))
                else: log(f"reel {k} failed QC {info}", "WARN")
            except Exception as e: log(f"reel {k} failed: {e}", "WARN")
        # 8. QC long video
        ok, info = QC.check_video(master, vo.duration, vertical=False)
        log(f"QC long video: {ok} {info}")
        if not ok: raise RuntimeError(f"long video failed QC: {info}")
        srt = RN.srt(tl, os.path.join(out, "captions.srt"))
        title = (pkg.get("titles") or [room["spine"].get("headline") or room["spine"].get("title_candidates", ["What If?"])[0]])[0]
        desc = _description(pkg.get("description", ""), chs, room)
        # 9. upload long video scheduled (private until slot)
        vid = PUB.yt_upload(master, title, desc, pkg.get("tags", []), publish_at=slot_iso, ai_label=S("AI_LABEL_DEFAULT", bool))
        PUB.yt_thumbnail(vid, thumb); PUB.yt_captions(vid, srt); PUB.yt_playlist(vid, _playlist(d.get("family") or d["ptype"]))
        rel = {"title": title, "pinned": pkg.get("pinned_comment", ""), "reels": []}
        for k, (rf, rp, cov) in enumerate(reel_files):
            rel["reels"].append({"file": rf, "cover": cov, "caption": rp.get("caption", ""), "hook": rp.get("hook_text", ""), "format": rp.get("format")})
        json.dump(rel, open(os.path.join(out, "release.json"), "w"))
        assets = _persist(out, ep)
        st.update("Episodes", "episode_id", ep, {"title": title, "yt_id": vid, "status": "SCHEDULED", "release_tag": ep, "assets": assets, "updated": iso(),
                                               "cost_inr": round(_ep_cost(ep), 1)})
        log(f"SCHEDULED {vid} for {slot_iso}: {title}")
        return {"ok": True, "episode": ep, "yt": vid, "master": master, "reels": [r[0] for r in reel_files], "thumb": thumb, "title": title}
    except Exception as e:
        log(f"episode failed: {e}", "ERROR"); st.update("Episodes", "episode_id", ep, {"status": "FAILED", "notes": str(e)[:400], "updated": iso()})
        raise
    finally: flush_log()

def _strip_beats(script):
    lines, marks = [], []
    for raw in script.splitlines():
        if raw.strip().startswith("##"):
            marks.append(len([l for l in lines if l.strip() and not l.strip().startswith("[pause")])); continue
        lines.append(raw)
    clean = "\n".join(lines)
    return clean, marks

def anchor_shots(shots, budget):
    """Which shots get a NEW image. living/kling always do; the rest of the budget is spread evenly over still shots.
    Every other still/graphic reuses the nearest earlier image with a different camera move (wide / detail / pan)."""
    own = [i for i, s in enumerate(shots) if s["type"] in ("living", "kling")]
    stills = [i for i, s in enumerate(shots) if s["type"] == "still"]
    left = max(0, budget - len(own))
    if stills and left:
        step = len(stills) / min(left, len(stills))
        pick = sorted({stills[int(k * step)] for k in range(min(left, len(stills)))})
    else: pick = []
    first = next((i for i, s in enumerate(shots) if s["type"] in ("still", "graphic")), None)
    a = set(own) | set(pick)
    if first is not None and not (a & set(range(0, first + 1))): a.add(first)
    return sorted(a)

def _assets(shots, units, out, ep, budget=56):
    """Images only for anchor shots (cap = stills + living + kling), then clips. A failed paid asset falls back to reuse."""
    anchors = anchor_shots(shots, budget)
    img_paths, img_urls = {}, {}
    def get_img(i):
        s = shots[i]; p = os.path.join(out, f"img{i:03d}.jpg")
        try:
            path, url = M.still(s.get("prompt") or units[i]["text"], p, ep, seed=f"{ep}{i}")
            return i, path, url
        except Exception as e:
            log(f"image {i} failed: {e}", "WARN"); return i, None, None
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for i, p, u in ex.map(get_img, anchors):
            if p: img_paths[i] = p; img_urls[i] = u
    clips = {}
    def get_clip(i):
        s = shots[i]; p = os.path.join(out, f"clip{i:03d}.mp4")
        try:
            if s["type"] == "stock": return i, M.stock(s.get("search", "space"), p, ep)
            if s["type"] in ("living", "kling") and i in img_paths:
                return i, M.animate(img_urls.get(i), img_paths[i], (s.get("motion") or "") + ". " + (s.get("prompt") or ""), p, ep, hero=s["type"] == "kling")
        except Exception as e: log(f"clip {i} failed ({s['type']}): {e} -> still", "WARN")
        return i, None
    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        for i, c in ex.map(get_clip, [i for i, s in enumerate(shots) if s["type"] in ("stock", "living", "kling")]):
            if c: clips[i] = c
    return {"img": img_paths, "clips": clips, "segments": {}, "anchors": anchors}

def _render(files, shots, units, vo, out, ep):
    """Segment boundaries = narration unit starts. Long units are split into 2-3 shots (wide + detail) to keep a cut every ~5-7 s."""
    total = vo.duration; fps = RN.FPS
    bounds = [0.0] + [u["start"] for u in units[1:]] + [total]
    segs, rng = [], random.Random(ep); segmap = {}
    prev_img = None; reuse = 0
    for i, u in enumerate(units):
        s = shots[i]; a, b = bounds[i], bounds[i + 1]; dur = b - a
        n_total = int(round(b * fps)) - int(round(a * fps))
        if n_total <= 0: continue
        own = files["img"].get(i)
        img = own or prev_img
        reuse = 0 if own else reuse + 1
        if own: prev_img = own
        pieces = 1 if dur < 7.5 or s["type"] in ("graphic",) else (2 if dur < 13 else 3)
        cut = [int(n_total * k / pieces) for k in range(pieces + 1)]
        for k in range(pieces):
            nf = cut[k + 1] - cut[k]; p = os.path.join(out, f"seg{i:03d}_{k}.mp4")
            try:
                if k == 0 and i in files["clips"]:
                    RN.clip_segment(files["clips"][i], p, nf, loop=s["type"] == "stock")
                elif s["type"] == "graphic" and k == 0:
                    RN.graphic_segment(s.get("graphic") or {}, img, p, nf)
                elif img:
                    RN.parallax_segment(img, p, nf, seed=f"{ep}{i}{k}", detail=((k + reuse) % 2 == 1))
                else:
                    RN.graphic_segment({"label": "", "from": 0, "to": 0}, None, p, nf)
            except Exception as e:
                log(f"segment {i}.{k} failed: {e} -> fallback", "WARN")
                RN.graphic_segment({"label": "", "from": 0, "to": 0}, img, p, nf)
            segs.append(p)
            if k == 0: segmap[i] = p
    files["segments"] = {i: segmap.get(i, segs[0]) for i in range(len(shots))}
    video = RN.concat(segs, os.path.join(out, "video.mp4"))
    events = []
    for i, s in enumerate(shots):
        if s["type"] == "kling": events.append(("boom", units[i]["start"])); events.append(("riser", units[i]["start"]))
        elif units[i]["tag"] == "reveal": events.append(("whoosh", max(0, units[i]["start"] - 0.3)))
    mix = RN.score(total, ep, events, vo.wav_path)
    aud = RN.write_mix(mix, os.path.join(out, "mix.wav"))
    return RN.mux(video, aud, os.path.join(out, "master.mp4"))

def _description(desc, chs, room):
    body = desc.replace("Chapters", "Chapters\n" + "\n".join(f"{t} {n}" for t, n in chs) if len(chs) >= 3 else "")
    return body + "\n\nThis video uses AI-assisted visuals and narration over an original script. Science is simplified for storytelling."

def _playlist(ptype):
    from whatifs.data import FAMILY_PLAYLIST
    if ptype in FAMILY_PLAYLIST: return FAMILY_PLAYLIST[ptype]
    return {"cosmic": "What If: Space", "body": "What If: Your Body", "collective": "What If: Everyone On Earth"}.get(ptype, "What If")

def _mark_premise(premise, ep):
    st = store()
    for r in st.rows("Premises"):
        if r["premise"].lower() == premise.lower():
            st.update("Premises", "premise_id", r["premise_id"], {"status": "USED", "episode_id": ep, "used_at": iso()}); return
    st.append("Premises", [{"premise_id": "N" + ep, "grid": "N", "premise": premise, "status": "USED", "episode_id": ep, "used_at": iso()}])
    st.append("Banned", [{"phrase": premise.lower()[:80], "reason": "already made"}])

def _ep_cost(ep):
    t = 0.0
    for r in store().rows("Cost_Log"):
        if r.get("episode_id") == ep:
            try: t += float(r["inr"])
            except Exception: pass
    return t

def _persist(out, ep):
    """Keep reels + covers + release info in YOUR PRIVATE Google Drive until release (never public before launch)."""
    if FAKE: return {}
    ids = {}
    for f in sorted(os.listdir(out)):
        if re.match(r"(reel\d\.mp4|cover\d\.jpg|release\.json)$", f):
            try: ids[f] = PUB.drive_upload(os.path.join(out, f), f"{ep}_{f}", public=False)[0]
            except Exception as e: log(f"drive save failed for {f}: {e}", "WARN")
    return ids
