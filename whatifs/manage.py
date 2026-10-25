"""whatifs/manage.py v7.0 - scheduler, release (reels at launch), trend scout, learning loop, strategy evolution, guardian,
money reminders, monthly brief, setup + self-test. All automatic; the owner is emailed only for money, launch, monthly brief."""
from __future__ import annotations
import os, json, random, re, datetime as dt, subprocess, statistics
import requests
from zoneinfo import ZoneInfo
from whatifs.core import S, store, log, iso, parse_iso, now_utc, set_setting, status, flush_log, JOB, FAKE, env, DEFAULTS, TABS, month_spend, gheaders, WORK
from whatifs import prompts as P
from whatifs.models import ask, discover_models
from whatifs import publish as PUB
from whatifs import governor as G

ET = ZoneInfo("America/New_York")
DAYS = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}

def paused():
    if S("PAUSED", bool): return True
    pu = parse_iso(S("PAUSED_UNTIL"))
    if pu and pu > now_utc(): return True
    return False

def next_slots(n=3, after=None):
    after = after or now_utc(); hh, mm = [int(x) for x in S("PUBLISH_HOUR_ET").split(":")]
    days = [DAYS[d.strip()[:3]] for d in S("PUBLISH_DAYS").split(",") if d.strip()[:3] in DAYS]
    out, d0 = [], after.astimezone(ET).date()
    for k in range(0, 21):
        day = d0 + dt.timedelta(days=k)
        if day.weekday() not in days: continue
        rng = random.Random(str(day)); jit = rng.randint(-S("PUBLISH_JITTER_MIN", int), S("PUBLISH_JITTER_MIN", int))
        t = dt.datetime(day.year, day.month, day.day, hh, mm, tzinfo=ET) + dt.timedelta(minutes=jit)
        t = t.replace(minute=(t.minute // 5) * 5, second=0)
        if t.astimezone(dt.timezone.utc) > after: out.append(t.astimezone(dt.timezone.utc))
        if len(out) >= n: break
    return out

def tick():
    """Hourly. Decides whether to produce the next episode and whether a release is due."""
    JOB["name"] = "tick"
    if paused(): log("paused - nothing to do"); return {"action": "paused"}
    if not S("VOICE"):
        t = parse_iso(S("VOICE_SAMPLES_AT"))
        if not t: return {"action": "waiting_for_voice_samples"}
        if now_utc() - t > dt.timedelta(hours=S("VOICE_WAIT_HOURS", float)):
            set_setting("VOICE", "A"); log("no voice picked in time - using A")
        else:
            return {"action": "waiting_for_voice_pick"}
    eps = store().rows("Episodes")
    due = []
    for e in eps:
        if e.get("status") == "SCHEDULED":
            t = parse_iso(e.get("slot_et"))
            if t and now_utc() >= t + dt.timedelta(minutes=S("REEL1_DELAY_MIN", int)): due.append(("release1", e["episode_id"]))
        if e.get("status") == "LIVE1":
            t = parse_iso(e.get("slot_et"))
            if t and now_utc() >= t + dt.timedelta(minutes=S("REEL2_DELAY_MIN", int)): due.append(("release2", e["episode_id"]))
    for e in eps:
        if e.get("status") == "SCHEDULED" and str(e.get("kill", "")).upper().startswith("KILL") and e.get("yt_id"):
            PUB.yt_set_privacy(e["yt_id"], "private"); store().update("Episodes", "episode_id", e["episode_id"], {"status": "KILLED"})
            log(f"{e['episode_id']} killed by owner before release")
    if due: return {"action": due[0][0], "episode": due[0][1]}
    busy = [e for e in eps if e.get("status") in ("PLANNING", "VOICING", "VISUALS")]
    stale = [e for e in busy if (now_utc() - (parse_iso(e.get("updated")) or now_utc())).total_seconds() > 6 * 3600]
    for e in stale: store().update("Episodes", "episode_id", e["episode_id"], {"status": "FAILED", "notes": "timed out"})
    if [e for e in busy if e not in stale]: return {"action": "busy"}
    taken = {e.get("slot_et") for e in eps if e.get("status") in ("SCHEDULED", "LIVE1", "LIVE")}
    for slot in next_slots(4):
        s = slot.strftime("%Y-%m-%dT%H:%M:%SZ")
        if s in taken: continue
        hours = (slot - now_utc()).total_seconds() / 3600
        fails = [e for e in eps if e.get("slot_et") == s and e.get("status") == "FAILED"]
        if hours <= S("PRODUCE_AHEAD_HOURS", float) and len(fails) < 2: return {"action": "produce", "slot": s}
        if len(fails) >= 2: continue
        break
    return {"action": "idle"}

def release(ep_id, which):
    """Reel k goes to YouTube Shorts + Instagram + Facebook once the long video is live. Pins the comment."""
    JOB["name"] = "release"; JOB["episode"] = ep_id
    st = store(); e = next(x for x in st.rows("Episodes") if x["episode_id"] == ep_id)
    if str(e.get("kill", "")).upper().startswith("KILL"):
        PUB.yt_set_privacy(e["yt_id"], "private"); st.update("Episodes", "episode_id", ep_id, {"status": "KILLED"}); log("killed by owner"); return
    rel = _fetch_release(ep_id, e.get("assets"))
    k = 0 if which == "release1" else 1
    if k == 0:
        if PUB.yt_status(e["yt_id"]) != "public": log("long video not public yet - waiting", "WARN"); return
        PUB.yt_comment(e["yt_id"], rel.get("pinned", ""))
    long_url = f"https://youtu.be/{e['yt_id']}"
    upd = {"status": "LIVE1" if k == 0 else "LIVE", "updated": iso()}
    if k < len(rel.get("reels", [])):
        r = rel["reels"][k]; path = r["file"]
        cap = f"{r['caption']}\n\nFull video: {long_url}"
        try:
            sid = PUB.yt_upload(path, (r.get("hook") or rel["title"])[:80] + " #shorts", cap + "\n#shorts", ["shorts", "what if"], ai_label=S("AI_LABEL_DEFAULT", bool), short=True)
            upd[f"reel{k+1}_yt"] = sid
            PUB.yt_comment(sid, f"Full video: {long_url}")
        except Exception as x: log(f"short upload failed: {x}", "WARN")
        if S("META_ON", bool):
            try:
                fid, url = PUB.drive_upload(path, os.path.basename(path), public=True)
                cfid, curl = PUB.drive_upload(r["cover"], os.path.basename(r["cover"]), public=True) if r.get("cover") else (None, None)
                upd[f"ig{k+1}"] = PUB.ig_reel(url, cap.replace(long_url, "link in bio"), curl)
                upd[f"fb{k+1}"] = PUB.fb_reel(url, cap)
                PUB.drive_private(fid)
                if cfid: PUB.drive_private(cfid)
            except Exception as x: log(f"meta post failed: {x}", "WARN")
    st.update("Episodes", "episode_id", ep_id, upd)
    if not S("LAUNCH_DONE", bool) and k == 0:
        PUB.email("We're live", f"<p>Your first video is live: <a href='{long_url}'>{long_url}</a></p><p>Nothing to do. The channel now runs on its own.</p>")
        set_setting("LAUNCH_DONE", "TRUE")
    flush_log()

def _fetch_release(ep_id, assets=None):
    d = os.path.join(WORK, ep_id); os.makedirs(d, exist_ok=True); path = os.path.join(d, "release.json")
    if not os.path.exists(path):
        ids = assets if isinstance(assets, dict) else json.loads(assets or "{}")
        for name, fid in ids.items():
            PUB.drive_download(fid, os.path.join(d, name))
    rel = json.load(open(path))
    for r in rel.get("reels", []):
        for key in ("file", "cover"):
            if r.get(key): r[key] = os.path.join(d, os.path.basename(r[key]))
    return rel

# ---------------- trend scout (weekly) ----------------
def trend_scout():
    JOB["name"] = "trends"
    api = []
    if not FAKE:
        try:
            after = (now_utc() - dt.timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
            for q in ["what if", "what would happen if", "science explained", "space facts"]:
                r = requests.get("https://www.googleapis.com/youtube/v3/search", headers=gheaders(), params={"part": "snippet", "q": q, "type": "video",
                                 "order": "viewCount", "publishedAfter": after, "maxResults": 10, "relevanceLanguage": "en", "regionCode": "US"}, timeout=30).json()
                ids = ",".join(i["id"]["videoId"] for i in r.get("items", []))
                if ids:
                    v = requests.get("https://www.googleapis.com/youtube/v3/videos", headers=gheaders(), params={"part": "snippet,statistics,contentDetails", "id": ids}, timeout=30).json()
                    for x in v.get("items", []):
                        api.append({"title": x["snippet"]["title"], "channel": x["snippet"]["channelTitle"], "views": x["statistics"].get("viewCount"),
                                    "len": x["contentDetails"]["duration"]})
            ch = requests.get("https://www.googleapis.com/youtube/v3/videos", headers=gheaders(), params={"part": "snippet,statistics", "chart": "mostPopular",
                              "regionCode": "US", "videoCategoryId": "28", "maxResults": 15}, timeout=30).json()
            for x in ch.get("items", []): api.append({"chart": "US science top", "title": x["snippet"]["title"], "channel": x["snippet"]["channelTitle"], "views": x["statistics"].get("viewCount")})
            api += _outliers()
        except Exception as e: log(f"youtube trend pull failed: {e}", "WARN")
        try:
            rss = requests.get("https://trends.google.com/trending/rss?geo=US", timeout=30).text
            api.append({"google_trends_us": re.findall(r"<title>([^<]+)</title>", rss)[1:20]})
        except Exception as e: log(f"google trends failed: {e}", "WARN")
    rep = ask("research", P.fill(P.TRENDS, channels=S("TREND_CHANNELS"), api=json.dumps(api[:40])), "Research now. Return the JSON only.",
              search=True, fake_key="research", temperature=0.3)
    wk = now_utc().strftime("%G-W%V"); rows = []
    for x in rep.get("exploding", [])[:12]: rows.append({"week": wk, "kind": "exploding", "item": x.get("title", ""), "detail": json.dumps(x.get("patterns", {}))[:900], "source": x.get("channel", "")})
    for x in rep.get("rules_for_room", [])[:8]: rows.append({"week": wk, "kind": "rule", "item": x, "detail": "", "source": "trend scout"})
    for x in rep.get("rising_angles", [])[:6]: rows.append({"week": wk, "kind": "angle", "item": x, "detail": "", "source": "trend scout"})
    crit = []
    for x in rep.get("platform_changes", [])[:8]:
        rows.append({"week": wk, "kind": "platform", "item": x.get("change", ""), "detail": x.get("severity", ""), "source": x.get("source", "")})
        if x.get("severity") == "critical" and re.search(r"\b(ai|synthetic|inauthentic|mass[- ]produced|repetitive)\b", x.get("change", "").lower()) and "monet" in x.get("change", "").lower():
            crit.append(x)
    store().append("Trend_Brief", rows)
    if crit: guardian(crit)
    flush_log(); return rep

def _outliers():
    """Latest uploads of the watched channels; flag videos with views >= 2x the channel's recent median (exploding)."""
    out = []
    for h in [x.strip() for x in S("TREND_CHANNELS").split(",") if x.strip()][:10]:
        try:
            c = requests.get("https://www.googleapis.com/youtube/v3/channels", headers=gheaders(), params={"part": "contentDetails", "forHandle": h}, timeout=30).json()
            up = c["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
            pl = requests.get("https://www.googleapis.com/youtube/v3/playlistItems", headers=gheaders(), params={"part": "contentDetails", "playlistId": up, "maxResults": 15}, timeout=30).json()
            ids = ",".join(i["contentDetails"]["videoId"] for i in pl.get("items", []))
            v = requests.get("https://www.googleapis.com/youtube/v3/videos", headers=gheaders(), params={"part": "snippet,statistics,contentDetails", "id": ids}, timeout=30).json().get("items", [])
            views = [int(x["statistics"].get("viewCount", 0)) for x in v]
            if not views: continue
            med = statistics.median(views) or 1
            for x in v:
                r = int(x["statistics"].get("viewCount", 0)) / med
                if r >= 2: out.append({"channel": h, "title": x["snippet"]["title"], "x_median": round(r, 1), "len": x["contentDetails"]["duration"]})
        except Exception as e: log(f"outlier scan {h} failed: {e}", "WARN")
    return out

def guardian(items):
    """Option B: pause only on a serious AI-monetisation rule change; auto-resume after 7 days."""
    until = (now_utc() + dt.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    set_setting("PAUSED_UNTIL", until)
    PUB.email("Paused for 7 days (policy watch)", "<p>A possible change to AI-content monetisation rules was found:</p><ul>" +
              "".join(f"<li>{i.get('change')} ({i.get('source')})</li>" for i in items) +
              f"</ul><p>Publishing resumes automatically on {until[:10]}. To resume now, set PAUSED_UNTIL to blank in Settings.</p>")
    log(f"guardian pause until {until}", "WARN")

# ---------------- learning loop (daily) ----------------
def learn():
    JOB["name"] = "learn"; st = store()
    eps = [e for e in st.rows("Episodes") if e.get("status") in ("LIVE1", "LIVE") and e.get("yt_id")]
    done = {a["episode_id"] for a in st.rows("Analytics")}
    rows = []
    for e in eps:
        t = parse_iso(e.get("slot_et"))
        if not t or e["episode_id"] in done or now_utc() - t < dt.timedelta(hours=72): continue
        m = _analytics(e["yt_id"], t)
        if not m: continue
        if m.get("ctr_kind") != "real":
            prev = [float(a.get("views") or 0) for a in st.rows("Analytics")[-10:]] + [float(r["views"]) for r in rows]
            base = (sorted(prev)[len(prev) // 2] if prev else 0) or max(1.0, float(m["views"]))
            m["ctr"] = round(min(0.15, 0.05 * float(m["views"]) / base), 4); m["ctr_kind"] = "proxy: 72h views vs channel median"
        score = round(m["ret30"] * 0.4 + m["avg_view_pct"] / 100 * 0.4 + min(m["ctr"], 0.15) / 0.15 * 0.2, 4)
        m.update({"episode_id": e["episode_id"], "yt_id": e["yt_id"], "pulled": iso(), "score": score}); rows.append(m)
        d = json.loads(e.get("draw_json") or "{}")
        for dim, name in d.get("strategies", {}).items():
            for r in st.rows("Strategies"):
                if r["dimension"] == dim and r["name"] == name:
                    st.update("Strategies", "name", name, {"plays": int(float(r.get("plays") or 0)) + 1,
                              "score_sum": round(float(r.get("score_sum") or 0) + score, 4), "score_n": int(float(r.get("score_n") or 0)) + 1})
    if rows: st.append("Analytics", rows)
    _evolve(); _length_rule(); flush_log()

def _analytics(vid, t):
    if FAKE:
        r = random.Random(vid); return {"views": r.randint(200, 9000), "avg_view_pct": r.uniform(25, 55), "avg_view_sec": r.uniform(120, 330), "ret30": r.uniform(0.5, 0.8),
                                        "ctr": 0.0, "ctr_kind": "proxy", "likes": 10, "shares": 2, "subs": 3}
    try:
        p = {"ids": "channel==MINE", "startDate": t.strftime("%Y-%m-%d"), "endDate": now_utc().strftime("%Y-%m-%d"), "filters": f"video=={vid}",
             "metrics": "views,averageViewPercentage,averageViewDuration,likes,shares,subscribersGained"}
        a = requests.get("https://youtubeanalytics.googleapis.com/v2/reports", headers=gheaders(), params=p, timeout=30).json()
        row = (a.get("rows") or [[0, 0, 0, 0, 0, 0]])[0]
        rp = dict(p, metrics="audienceWatchRatio", dimensions="elapsedVideoTimeRatio")
        ret = requests.get("https://youtubeanalytics.googleapis.com/v2/reports", headers=gheaders(), params=rp, timeout=30).json().get("rows", [])
        ret30 = next((r[1] for r in ret if r[0] >= 0.05), 0.6)
        ctr, kind = 0.0, "proxy"
        try:
            cp = dict(p, metrics="videoThumbnailImpressionsClickRate"); cr = requests.get("https://youtubeanalytics.googleapis.com/v2/reports", headers=gheaders(), params=cp, timeout=30).json()
            ctr = float(cr["rows"][0][0]) / 100; kind = "real"
        except Exception: pass
        return {"ctr_kind": kind, "views": row[0], "avg_view_pct": row[1], "avg_view_sec": row[2], "likes": row[3], "shares": row[4], "subs": row[5], "ret30": float(ret30), "ctr": ctr}
    except Exception as e: log(f"analytics failed for {vid}: {e}", "WARN"); return None

def _evolve():
    """Cut a clearly weak strategy (>=5 plays, mean < pool mean - 0.08) and invent a replacement. Never fewer than 5 active."""
    st = store(); rows = st.rows("Strategies")
    rules = [r["item"] for r in st.rows("Trend_Brief") if r["kind"] == "rule"][-8:]
    for dim in {r["dimension"] for r in rows}:
        act = [r for r in rows if r["dimension"] == dim and r["status"] == "ACTIVE"]
        scored = [r for r in act if float(r.get("score_n") or 0) >= 5]
        if len(scored) < 3: continue
        means = {r["name"]: float(r["score_sum"]) / float(r["score_n"]) for r in scored}
        pool = statistics.mean(means.values()); worst = min(means, key=means.get)
        if means[worst] < pool - 0.08:
            st.update("Strategies", "name", worst, {"status": "RETIRED"})
            best = sorted(means, key=means.get, reverse=True)[:2]
            try:
                new = ask("sonnet", P.fill(P.STRATEGY_NEW, dim=dim, best=json.dumps({b: next(r["definition"] for r in act if r["name"] == b) for b in best}),
                          rules=json.dumps(rules), names=[r["name"] for r in rows if r["dimension"] == dim]), "Invent now.", fake_key="strategy")
                if new.get("name") and new.get("definition"):
                    st.append("Strategies", [{"dimension": dim, "name": new["name"][:40], "definition": new["definition"][:400], "status": "ACTIVE",
                                              "plays": 0, "score_sum": 0, "score_n": 0, "created": iso(), "source": "learned"}])
                    st.append("Lessons", [{"ts": iso(), "lesson": f"{dim}: retired {worst}, added {new['name']}", "evidence": json.dumps(means), "applies_to": dim}])
            except Exception as e:
                st.update("Strategies", "name", worst, {"status": "ACTIVE"}); log(f"evolve failed, kept {worst}: {e}", "WARN")

def _length_rule():
    a = store().rows("Analytics")
    if len(a) < 10: return
    eps = {e["episode_id"]: json.loads(e.get("draw_json") or "{}") for e in store().rows("Episodes")}
    pairs = [(eps.get(x["episode_id"], {}).get("runtime_sec", 0), float(x["avg_view_sec"])) for x in a if eps.get(x["episode_id"])]
    long_ = [s for r, s in pairs if r >= 600]; short = [s for r, s in pairs if r < 600]
    if len(long_) >= 4 and len(short) >= 4 and statistics.mean(long_) > statistics.mean(short) * 1.15:
        new = min(S("RUNTIME_HARD_MAX_SEC", int), S("RUNTIME_MAX_SEC", int) + 60)
        if new != S("RUNTIME_MAX_SEC", int):
            set_setting("RUNTIME_MAX_SEC", str(new)); store().append("Lessons", [{"ts": iso(), "lesson": f"longer videos earn more watch time: max runtime -> {new}s", "evidence": "", "applies_to": "runtime"}])

# ---------------- money ----------------
def failure_watch():
    """One email if 3 episodes in a row failed (repair bot may be capped). Never more than once per 3 days."""
    eps = store().rows("Episodes")[-3:]
    if len(eps) == 3 and all(e.get("status") == "FAILED" for e in eps):
        last = parse_iso(S("FAIL_MAIL_AT")) if "FAIL_MAIL_AT" in settings_keys() else None
        if not last or now_utc() - last > dt.timedelta(days=3):
            PUB.email("Needs a look (3 failed tries)", "<p>The last 3 episode attempts failed. Reasons:</p><ul>" +
                      "".join(f"<li>{e.get('notes','')[:200]}</li>" for e in eps) +
                      "</ul><p>Open this chat with Claude and paste the Run_Log tab, or ask Gemini whether it is an account/key issue. Publishing retries hourly.</p>")
            set_setting("FAIL_MAIL_AT", iso())

def settings_keys():
    return {r["key"] for r in store().rows("Settings")}

def money_check():
    JOB["name"] = "money"; msgs = []
    failure_watch()
    if S("AUTO_RELOAD_ON", bool): return
    for prov, url, name in (("fal", "https://fal.ai/dashboard/billing", "fal.ai"), ("anthropic", "https://console.anthropic.com/settings/billing", "Anthropic")):
        days = G.runway_days(prov)
        if days <= S("REFILL_WARN_DAYS", int):
            msgs.append(f"<li><b>{name}</b>: about {days:.0f} days left. <a href='{url}'>Top up here</a>, then add the amount to the {prov.upper() if prov=='fal' else 'ANTHROPIC'}_FUNDED_USD cell (or switch on auto-reload and set AUTO_RELOAD_ON to TRUE).</li>")
    if msgs: PUB.email("Top-up reminder", "<ul>" + "".join(msgs) + "</ul><p>If you do nothing, the channel keeps publishing on free fallbacks.</p>")

def monthly_brief():
    JOB["name"] = "brief"; st = store()
    data = {"analytics": st.rows("Analytics")[-15:], "spend_month": month_spend(), "cap": G.cap_inr(), "revenue": st.rows("Revenue_Log")[-3:],
            "lessons": st.rows("Lessons")[-10:], "trends": [r["item"] for r in st.rows("Trend_Brief")[-15:]]}
    txt = ask("sonnet", P.fill(P.BRIEF, data=json.dumps(data, default=str)[:20000]), "Write it.", want_json=False, fake_key="brief")
    PUB.email("Monthly brief", "<pre style='font-family:sans-serif;white-space:pre-wrap'>" + txt + "</pre>")

# ---------------- setup ----------------
def setup():
    JOB["name"] = "setup"; st = store()
    st.ensure_tabs()
    have = {r["key"] for r in st.rows("Settings")}
    st.append("Settings", [{"key": k, "value": v[0], "note": v[1]} for k, v in DEFAULTS.items() if k not in have])
    if env("OWNER_EMAIL") and not S("OPERATOR_EMAIL"): set_setting("OPERATOR_EMAIL", env("OWNER_EMAIL"))
    from whatifs.data import premise_rows, BANNED, strategy_rows
    if not st.rows("Premises"): st.append("Premises", premise_rows())
    if not st.rows("Banned"): st.append("Banned", [{"phrase": p, "reason": r} for p, r in BANNED])
    if not st.rows("Strategies"): st.append("Strategies", strategy_rows())
    status("sheet_ready", True, f"{len(TABS)} tabs")
    if not FAKE:
        from whatifs.models import selftest
        selftest()
        try:
            ch = PUB.yt_channel(); status("youtube_connected", bool(ch.get("id")), ch.get("snippet", {}).get("title", ""))
            lv = ch.get("status", {}).get("longUploadsStatus", "")
            status("youtube_phone_verified", lv in ("allowed", "eligible"), lv or "unknown - verify at youtube.com/verify")
        except Exception as e: status("youtube_connected", False, str(e)[:300])
        try:
            r = requests.get("https://api.anthropic.com/v1/models", headers={"x-api-key": env("ANTHROPIC_KEY"), "anthropic-version": "2023-06-01"}, timeout=20)
            status("anthropic_key", r.status_code == 200, r.status_code)
        except Exception as e: status("anthropic_key", False, str(e))
        try:
            from whatifs.media import still
            p, u = still("a small blue marble on black velvet", "fal_test.jpg", "setup", seed="t", w=256, h=256)
            status("fal_works", os.path.exists(p), "test image made")
        except Exception as e: status("fal_works", False, str(e)[:300])
        if S("META_ON", bool): _meta_ids()
        status("pexels_key", bool(env("PEXELS_KEY")), "optional")
    flush_log()

def _meta_ids():
    try:
        k = env("META_PAGE_KEY"); GV = "https://graph.facebook.com/v21.0/"
        me = requests.get(GV + "me", headers={"Authorization": "Bearer " + k}, params={"fields": "id,name,instagram_business_account"}, timeout=30).json()
        if "id" in me: set_setting("FB_PAGE_ID", me["id"])
        ig = (me.get("instagram_business_account") or {}).get("id")
        if ig: set_setting("IG_USER_ID", ig)
        status("meta_connected", bool(me.get("id") and ig), json.dumps({"page": me.get("name"), "ig": ig}))
    except Exception as e: status("meta_connected", False, str(e)[:300])
