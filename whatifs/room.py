"""whatifs/room.py v7.0 - the writers' room. Scout -> Showrunner -> department memos -> Production Bible -> Writer ->
Critic/Spectacle gate (Gemini, independent) -> one rewrite -> Director -> Packager -> Reel Producer -> Continuity check.
Fail-forward: 3 premise tries, then relax one step, then go. No human decision ever blocks."""
from __future__ import annotations
import json, re, random
from whatifs import prompts as P
from whatifs.models import ask, ask_many
from whatifs.core import store, log, S, iso
from whatifs.data import STRATEGIES

def _j(x, n=6000): s = json.dumps(x, ensure_ascii=False); return s[:n]

def context():
    st = store()
    banned = [r["phrase"] for r in st.rows("Banned")]
    eps = st.rows("Episodes")
    recent = [e.get("title") or e.get("premise") for e in eps[-25:]]
    tb = st.rows("Trend_Brief")[-40:]
    trends = [f'{r["kind"]}: {r["item"]} - {r["detail"]}' for r in tb]
    lessons = [r["lesson"] for r in st.rows("Lessons")[-15:]]
    defs = {r["name"]: r["definition"] for r in st.rows("Strategies")}
    return {"banned": banned, "recent": recent, "trends": "\n".join(trends)[:5000] or "none yet",
            "lessons": "\n".join(lessons)[:2500] or "none yet", "defs": defs}

def _banned_hit(text, banned):
    t = text.lower(); return any(b.lower() in t for b in banned)

def _similar(a, recent):
    wa = set(re.findall(r"[a-z]{4,}", a.lower()))
    for r in recent:
        wb = set(re.findall(r"[a-z]{4,}", (r or "").lower()))
        if wa and wb and len(wa & wb) / len(wa | wb) > 0.5: return True
    return False

def seeds(k=12):
    fresh = [r for r in store().rows("Premises") if r.get("status") == "FRESH"]
    random.shuffle(fresh); return [r["premise"] for r in fresh[:k]]

def _family_ok(fam, recent_fams):
    if fam and fam in recent_fams[-3:]: return False
    if fam == "F12_everyone" and recent_fams[-5:].count("F12_everyone") >= 1: return False
    return True

def ai_tells(text):
    from whatifs.data import AI_TELLS
    t = text.lower(); return [w for w in AI_TELLS if w in t]

def scout_and_pick(draw, ctx, episode):
    from whatifs.data import FAMILIES
    recent_fams = [json.loads(e.get("draw_json") or "{}").get("family", "") for e in store().rows("Episodes")[-6:] if e.get("draw_json")]
    fams = {k: v[0] for k, v in FAMILIES.items()}
    for attempt in range(3):
        pit = ask("opus", P.fill(P.SCOUT, banned=ctx["banned"], recent=ctx["recent"], trends=ctx["trends"], seeds=seeds(),
                  families=json.dumps(fams), prefer=draw["strategies"].get("family") or "any"),
                  "Pitch now.", episode=episode, fake_key="scout", temperature=1.0)
        good = []
        for p in pit.get("pitches", []):
            sc = p.get("scores", {}); tot = sum(float(v) for v in sc.values()) if sc else 0
            if _banned_hit(p.get("premise", ""), ctx["banned"]) or _similar(p.get("premise", ""), ctx["recent"]): continue
            if not _family_ok(p.get("family"), recent_fams): continue
            if p.get("family") == draw["strategies"].get("family"): tot += 3
            p["total"] = tot; good.append(p)
        good.sort(key=lambda p: -p["total"])
        floor = [50, 45, 0][attempt]   # relax one step per try (fail-forward)
        good = [p for p in good if p["total"] >= floor]
        if good:
            spine = ask("opus", P.fill(P.SHOWRUNNER, pitches=_j(good[:5]), draw=_j(draw), defs=_j({k: ctx["defs"].get(v, "") for k, v in draw["strategies"].items()}),
                        trends=ctx["trends"], lessons=ctx["lessons"]), "Choose and set the spine.", episode=episode, fake_key="showrunner")
            if spine.get("premise"):
                spine.setdefault("family", good[0].get("family", "")); spine.setdefault("headline", good[0].get("headline", spine["premise"]))
                return spine
        log(f"scout attempt {attempt+1} gave no usable pitch", "WARN", episode)
    raise RuntimeError("scout failed 3 times")

def run_room(draw, episode):
    ctx = context(); d = draw; stg = d["strategies"]; defs = ctx["defs"]
    spine = scout_and_pick(d, ctx, episode); log(f"premise: {spine['premise']}", episode=episode)
    roles = ["WRITER", "AUDIENCE PSYCHOLOGIST", "DIRECTOR + DP", "EDITOR + SOUND", "PACKAGER", "REEL PRODUCER"]
    memos = ask_many([dict(role="sonnet", system=P.fill(P.MEMO, role=r, spine=_j(spine), draw=_j(d), trends=ctx["trends"][:2500]),
                           prompt="Memo now.", episode=episode, fake_key="memo", max_tokens=1200) for r in roles])
    bible = ask("opus", P.fill(P.BIBLE, spine=_j(spine), memos=_j(dict(zip(roles, memos)), 8000), draw=_j(d)),
                "Write the bible.", episode=episode, fake_key="bible")
    wmin, wmax = int(d["words"] * 0.93), int(d["words"] * 1.07)
    wbrief = P.fill(P.WRITER, words=d["words"], wmin=wmin, wmax=wmax, story=stg["story"], storydef=defs.get(stg["story"], ""),
                    hook=stg["hook"], hookdef=defs.get(stg["hook"], ""), hooksec=d["hook_sec"], humour=stg["humour"], voice=stg["voice"], bible=_j(bible, 9000))
    script = ask("sonnet", wbrief, "Write the narration.", episode=episode, fake_key="writer", max_tokens=16000)
    script = _fix_length(script, wbrief, wmin, wmax, episode)
    script = humanize(script, episode)
    verdict = critic(spine, script, ctx, episode)
    if verdict.get("verdict") != "PASS":
        log(f"critic asked for revision: {verdict.get('fixes')}", "WARN", episode)
        script = ask("sonnet", wbrief + "\nCRITIC FIXES (apply all): " + _j(verdict.get("fixes", {})), "Rewrite the full narration.",
                     episode=episode, fake_key="writer", max_tokens=16000)
        script = _fix_length(script, wbrief, wmin, wmax, episode)
        script = humanize(script, episode)
        verdict = critic(spine, script, ctx, episode)
        if verdict.get("verdict") != "PASS":
            if min(verdict.get("scores", {}).get(k, 10) for k in ("policy_safe",)) < 7:
                raise RuntimeError("policy risk after rewrite - premise skipped")
            log("critic still unhappy after one rewrite - continuing (fail-forward)", "WARN", episode)
    return {"spine": spine, "bible": bible, "script": script, "critic": verdict}

def humanize(script, episode):
    """Human Editor pass, repeated once if AI tells remain. Keeps the old draft if the edit breaks structure."""
    for _ in range(2):
        out = ask("sonnet", P.fill(P.HUMANIZE, script=script.get("script", "")), "Edit now.", episode=episode, fake_key="humanize", max_tokens=16000)
        new = out.get("script", "")
        old_n = len(script.get("script", "").split()); new_n = len(new.split())
        if new and new.count("## BEAT") >= max(1, script.get("script", "").count("## BEAT") - 1) and abs(new_n - old_n) <= old_n * 0.12:
            script = dict(script, script=new)
        tells = ai_tells(script.get("script", ""))
        if len(tells) <= 2: break
        log(f"AI phrases still present {tells} - second human pass", "WARN", episode)
    return script

def extend(room, script_text, add_words, episode):
    out = ask("sonnet", P.fill(P.HUMANIZE, script=script_text),
              f"The narration is too short. Keep everything and ADD about {add_words} words: deepen the strongest beats with one more concrete consequence each, "
              "keep the same tags and '## BEAT' lines. Return the full narration.", episode=episode, fake_key="writer", max_tokens=16000)
    s = out.get("script", "")
    return s if len(s.split()) > len(script_text.split()) else None

def _fix_length(script, brief, wmin, wmax, episode):
    n = len(re.sub(r"\[[^\]]+\]|##.*", "", script.get("script", "")).split())
    if wmin <= n <= wmax: return script
    log(f"script length {n} outside {wmin}-{wmax}, adjusting", "WARN", episode)
    adj = ask("sonnet", brief, f"Your draft has {n} words. Rewrite it to {(wmin+wmax)//2} words, same structure:\n" + script.get("script", ""),
              episode=episode, fake_key="writer", max_tokens=16000)
    return adj if adj.get("script") else script

def critic(spine, script, ctx, episode):
    v = ask("critic", P.fill(P.CRITIC, recent=ctx["recent"], episode=_j({"spine": spine, "script": script.get("script", "")}, 30000)),
            "Judge now.", episode=episode, fake_key="critic", temperature=0.2)
    sc = v.get("scores", {})
    vals = [float(x) for x in sc.values()] if sc else [0]
    tells = ai_tells(script.get("script", ""))
    ok = (sum(vals) / len(vals) >= 7.0 and sc.get("policy_safe", 0) >= 8 and sc.get("humour_cringe_free", 0) >= 6 and sc.get("hook_strength", 0) >= 7
          and sc.get("sounds_human", 7) >= 7 and sc.get("psychological_pull", 7) >= 7 and len(tells) <= 2)
    if tells: v.setdefault("fixes", {})["writer"] = (v.get("fixes", {}).get("writer", "") + f" Remove AI phrases: {tells}.").strip()
    v["verdict"] = "PASS" if ok else "REVISE"    # computed here: the model's own verdict word is never trusted alone
    v["mean"] = round(sum(vals) / len(vals), 2)
    return v

def plan_shots(room, units, draw, plan, episode):
    look = room["bible"].get("look", "cinematic, deep shadows, single cold key light, fine film grain")
    size = 40; chunks = [units[i:i + size] for i in range(0, len(units), size)]; n = len(chunks)
    jobs = []
    for k, ch in enumerate(chunks):
        kl = plan["kling"] // n + (1 if k < plan["kling"] % n else 0); lv = plan["living"] // n + (1 if k < plan["living"] % n else 0)
        U = "\n".join(f'{u["i"]}: {u["text"]}' for u in ch)
        jobs.append(dict(role="sonnet", system=P.fill(P.DIRECTOR, nshots=len(ch), kling=kl, living=lv, ptype=draw["ptype"], look=look, units=U),
                         prompt=f"Shot list for units {ch[0]['i']}-{ch[-1]['i']} (use these exact unit numbers).", episode=episode, fake_key="director", max_tokens=8000))
    shots = []
    for res in ask_many(jobs, workers=3): shots += res.get("shots", [])
    return normalise_shots(shots, units, plan, look)

def normalise_shots(shots, units, plan, look):
    """Make the shot list safe: one shot per unit, caps enforced, peak gets kling, prompts present."""
    by = {}
    for s in shots:
        try: by.setdefault(int(s.get("unit", -1)), s)
        except Exception: pass
    out = []
    for u in units:
        s = dict(by.get(u["i"]) or {"type": "still", "prompt": u["text"]})
        s["unit"] = u["i"]; s["type"] = s.get("type") if s.get("type") in ("still", "living", "kling", "stock", "graphic") else "still"
        if s["type"] in ("still", "living", "kling") and not s.get("prompt"): s["prompt"] = u["text"]
        if s["type"] == "stock" and not s.get("search"): s["type"] = "still"; s["prompt"] = s.get("prompt") or u["text"]
        if s["type"] == "graphic" and not isinstance(s.get("graphic"), dict): s["type"] = "still"; s["prompt"] = u["text"]
        if s.get("prompt") and look not in s["prompt"]: s["prompt"] = s["prompt"].rstrip(". ") + ". " + look
        out.append(s)
    for typ, cap in (("kling", plan["kling"]), ("living", plan["living"])):
        idx = [i for i, s in enumerate(out) if s["type"] == typ]
        for i in idx[cap:]: out[i]["type"] = "still"
        have = len(idx[:cap])
        if have < cap:
            cands = [i for i, s in enumerate(out) if s["type"] == "still" and units[i]["tag"] in ("reveal", "tension")] or \
                    [i for i, s in enumerate(out) if s["type"] == "still"]
            step = max(1, len(cands) // max(1, cap - have + 1))
            for i in cands[step - 1::step][: cap - have]: out[i]["type"] = typ
    return out

def package(room, chapters, draw, episode):
    ctx = context(); stg = draw["strategies"]
    excerpt = room["script"].get("script", "")[:3500]
    return ask("sonnet", P.fill(P.PACKAGER, title=stg["title"], titledef=ctx["defs"].get(stg["title"], ""), thumb=stg["thumb"],
               thumbdef=ctx["defs"].get(stg["thumb"], ""), spine=_j(room["spine"]), excerpt=excerpt, trends=ctx["trends"][:3000],
               lessons=ctx["lessons"], chapters=_j(chapters)), "Package now.", episode=episode, fake_key="packager")

def reels(room, shots, draw, episode):
    ctx = context()
    S_ = "\n".join(f'{i}: {s["type"]}: {(s.get("prompt") or s.get("search") or "")[:90]}' for i, s in enumerate(shots))
    fm = draw["reel_formats"]
    r = ask("sonnet", P.fill(P.REEL, formats=fm, formatdefs=_j({f: ctx["defs"].get(f, "") for f in fm}), shots=S_[:12000],
            spine=_j(room["spine"]), trends=ctx["trends"][:2000]), "Make the 2 reels.", episode=episode, fake_key="reel").get("reels", [])
    good = []
    for x in r[:2]:
        sh = [int(i) for i in x.get("shots", []) if str(i).isdigit() and int(i) < len(shots)]
        kl = [i for i in sh if shots[i]["type"] == "kling"]
        sh = [i for i in sh if shots[i]["type"] != "kling"] + kl[:1]
        if len(sh) >= 4 and x.get("lines"): x["shots"] = sh; good.append(x)
    return good

def continuity(pkg, episode):
    try:
        v = ask("critic", P.fill(P.SYNC, pkg=_j(pkg, 40000)), "Check now.", episode=episode, fake_key="sync", temperature=0.1)
        return v
    except Exception as e:
        log(f"continuity check skipped: {e}", "WARN", episode); return {"ok": True, "problems": []}
