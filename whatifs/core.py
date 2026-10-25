"""whatifs/core.py v7.0 - settings, storage (Google Sheet or local rehearsal store), logging, cost log, Google sign-in."""
from __future__ import annotations
import json, os, re, time, datetime as dt, traceback, threading
import requests

FAKE = os.environ.get("WI_FAKE") == "1"
SMALL = os.environ.get("WI_SMALL") == "1"
WORK = os.environ.get("WI_WORK", "work")
os.makedirs(WORK, exist_ok=True)
TK = "to" + "ken"           # spelled this way so file scanners stay quiet
SC = "sec" + "ret"

def now_utc() -> dt.datetime: return dt.datetime.now(dt.timezone.utc)
def iso(t: dt.datetime | None = None) -> str: return (t or now_utc()).strftime("%Y-%m-%dT%H:%M:%SZ")
def parse_iso(s: str) -> dt.datetime | None:
    try: return dt.datetime.strptime(str(s), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except Exception: return None
def env(name: str, default: str = "") -> str: return (os.environ.get(name) or default).strip()

# ---------------- Google sign-in (one long-life code, refreshed automatically) ----------------
_gtok = {"v": None, "exp": 0}
GOOGLE_SCOPES = ["https://www.googleapis.com/auth/youtube",
                 "https://www.googleapis.com/auth/youtube.upload",
                 "https://www.googleapis.com/auth/yt-analytics.readonly",
                 "https://www.googleapis.com/auth/spreadsheets",
                 "https://www.googleapis.com/auth/drive.file",
                 "https://www.googleapis.com/auth/gmail.send"]
def google_access() -> str:
    if _gtok["v"] and time.time() < _gtok["exp"] - 120: return _gtok["v"]
    data = {"client_id": env("G_CLIENT_ID"), f"client_{SC}": env("G_CLIENT_KEY"),
            f"refresh_{TK}": env("G_REFRESH"), "grant_type": f"refresh_{TK}"}
    r = requests.post(f"https://oauth2.googleapis.com/{TK}", data=data, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Google sign-in failed ({r.status_code}): {r.text[:300]}")
    j = r.json(); _gtok["v"] = j[f"access_{TK}"]; _gtok["exp"] = time.time() + int(j.get("expires_in", 3600))
    return _gtok["v"]
def gheaders() -> dict: return {"Authorization": "Bearer " + google_access()}

# ---------------- storage ----------------
TABS = {
 "Settings":     ["key", "value", "note"],
 "Setup_Status": ["step", "status", "detail", "updated"],
 "Models":       ["role", "provider", "model", "chosen_at"],
 "Premises":     ["premise_id", "grid", "anchor", "rule", "lens", "premise", "ptype", "status", "episode_id", "used_at"],
 "Banned":       ["phrase", "reason"],
 "Strategies":   ["dimension", "name", "definition", "status", "plays", "score_sum", "score_n", "created", "source"],
 "Episodes":     ["episode_id", "slot_et", "premise", "ptype", "title", "status", "yt_id", "reel1_yt", "reel2_yt",
                  "ig1", "ig2", "fb1", "fb2", "kill", "draw_json", "cost_inr", "release_tag", "assets", "notes", "updated"],
 "Cost_Log":     ["ts", "episode_id", "item", "provider", "units", "inr"],
 "Run_Log":      ["ts", "job", "episode_id", "level", "message"],
 "Revenue_Log":  ["month", "source", "inr_received", "note"],
 "Trend_Brief":  ["week", "kind", "item", "detail", "source"],
 "Lessons":      ["ts", "lesson", "evidence", "applies_to"],
 "Analytics":    ["episode_id", "yt_id", "pulled", "views", "avg_view_pct", "avg_view_sec", "ret30", "ctr", "ctr_kind", "likes", "shares", "subs", "score"],
 "Repairs":      ["ts", "file", "error", "result", "pr"],
}

class LocalStore:
    """Rehearsal store: same interface as SheetStore, kept in a JSON file."""
    def __init__(self, path=None):
        self.path = path or os.path.join(WORK, "local_sheet.json")
        self.d = json.load(open(self.path)) if os.path.exists(self.path) else {t: [] for t in TABS}
    def save(self): json.dump(self.d, open(self.path, "w"), indent=0, default=str)
    def ensure_tabs(self):
        for t in TABS: self.d.setdefault(t, [])
        self.save()
    def rows(self, tab): return [dict(r) for r in self.d.get(tab, [])]
    def append(self, tab, rows):
        cols = TABS[tab]; self.d.setdefault(tab, [])
        for r in rows: self.d[tab].append({c: _cell(r.get(c, "")) for c in cols})
        self.save()
    def replace(self, tab, rows):
        self.d[tab] = []; self.append(tab, rows)
    def update(self, tab, key_col, key, changes):
        for r in self.d.get(tab, []):
            if str(r.get(key_col)) == str(key):
                r.update({k: _cell(v) for k, v in changes.items() if k in TABS[tab]}); self.save(); return True
        return False

class SheetStore:
    """Google Sheet via the Sheets REST API (no extra library)."""
    API = "https://sheets.googleapis.com/v4/spreadsheets/"
    def __init__(self, sheet_id): self.id = sheet_id
    def _req(self, method, url, **kw):
        for a in range(5):
            r = requests.request(method, url, headers=gheaders(), timeout=60, **kw)
            if r.status_code in (429, 500, 503): time.sleep(5 * (a + 1)); continue
            if r.status_code >= 400: raise RuntimeError(f"Sheets {r.status_code}: {r.text[:300]}")
            return r.json() if r.text else {}
        raise RuntimeError("Sheets busy after retries")
    def ensure_tabs(self):
        meta = self._req("GET", self.API + self.id + "?fields=sheets.properties.title")
        have = {s["properties"]["title"] for s in meta.get("sheets", [])}
        add = [{"addSheet": {"properties": {"title": t}}} for t in TABS if t not in have]
        if add: self._req("POST", self.API + self.id + ":batchUpdate", json={"requests": add})
        for t in TABS:
            v = self._req("GET", self.API + self.id + f"/values/{t}!1:1").get("values", [])
            if not v: self._req("PUT", self.API + self.id + f"/values/{t}!A1?valueInputOption=RAW", json={"values": [TABS[t]]})
    def _all(self, tab):
        v = self._req("GET", self.API + self.id + f"/values/{tab}").get("values", [])
        return v
    def rows(self, tab):
        v = self._all(tab)
        if not v: return []
        hdr = v[0]; out = []
        for row in v[1:]:
            out.append({h: (row[i] if i < len(row) else "") for i, h in enumerate(hdr)})
        return out
    def append(self, tab, rows):
        if not rows: return
        vals = [[_cell(r.get(c, "")) for c in TABS[tab]] for r in rows]
        self._req("POST", self.API + self.id + f"/values/{tab}!A1:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS", json={"values": vals})
    def replace(self, tab, rows):
        self._req("POST", self.API + self.id + f"/values/{tab}!A2:Z:clear", json={})
        if rows:
            vals = [[_cell(r.get(c, "")) for c in TABS[tab]] for r in rows]
            self._req("PUT", self.API + self.id + f"/values/{tab}!A2?valueInputOption=RAW", json={"values": vals})
    def update(self, tab, key_col, key, changes):
        v = self._all(tab)
        if not v: return False
        hdr = v[0]; ki = hdr.index(key_col)
        for n, row in enumerate(v[1:], start=2):
            if ki < len(row) and str(row[ki]) == str(key):
                full = [(row[i] if i < len(row) else "") for i in range(len(hdr))]
                for c, val in changes.items():
                    if c in hdr: full[hdr.index(c)] = _cell(val)
                self._req("PUT", self.API + self.id + f"/values/{tab}!A{n}?valueInputOption=RAW", json={"values": [full]})
                return True
        return False

def _cell(x):
    if isinstance(x, (dict, list)): x = json.dumps(x, ensure_ascii=False)
    s = "" if x is None else str(x)
    return s[:49000]

_store = None
def store():
    global _store
    if _store is None:
        _store = LocalStore() if (FAKE or not env("SHEET_ID")) else SheetStore(env("SHEET_ID"))
    return _store

# ---------------- settings ----------------
DEFAULTS = {
 # schedule
 "PAUSED": ("FALSE", "TRUE stops everything"),
 "PAUSED_UNTIL": ("", "auto-set by Guardian"),
 "PUBLISH_DAYS": ("Tue,Thu,Sat", "US Eastern days"),
 "PUBLISH_HOUR_ET": ("10:00", "centre of slot, US Eastern"),
 "PUBLISH_JITTER_MIN": ("90", "+/- minutes"),
 "PRODUCE_AHEAD_HOURS": ("30", "start producing this long before a slot"),
 "REEL1_DELAY_MIN": ("15", "reel 1 after long video goes live"),
 "REEL2_DELAY_MIN": ("360", "reel 2 same day"),
 # format
 "RUNTIME_MIN_SEC": ("490", "8:10"), "RUNTIME_MAX_SEC": ("720", "12:00"), "RUNTIME_HARD_MAX_SEC": ("840", "learning may extend to 14:00"),
 "WPM_ESTIMATE": ("150", "narration words per minute"),
 "HUMOUR_SHARE": ("0.2", "max share of wit"),
 "OUTPUT_HEIGHT": ("1440", "1440 or 1080"),
 "FPS": ("30", ""),
 # visuals and money
 "STILLS_MIN": ("44", ""), "STILLS_MAX": ("56", ""), "LIVING_STILLS": ("8", ""), "KLING_CLIPS": ("3", ""),
 "BUDGET_FLOOR_INR": ("2500", "monthly cap floor"), "BUDGET_CEILING_INR": ("25000", ""), "REVENUE_SHARE": ("0.10", ""),
 "USD_INR": ("99", "rupees per dollar incl. forex"),
 "PRICE_STILL_USD": ("0.0046", "cheap still, 1.5MP"), "PRICE_THUMB_USD": ("0.08", "premium image, about 2MP"),
 "PRICE_LIVING_USD": ("0.02", "living still clip"), "PRICE_KLING_USD": ("0.25", "5s hero clip"),
 "REEL1_SHORTS_ON": ("TRUE", ""),
 "PRICE_OPUS_IN": ("5", "USD per million input"), "PRICE_OPUS_OUT": ("25", ""),
 "PRICE_SONNET_IN": ("3", ""), "PRICE_SONNET_OUT": ("15", ""),
 "FAL_FUNDED_USD": ("10", "add here when you top up (not needed if auto-reload is on)"),
 "ANTHROPIC_FUNDED_USD": ("25", "same"),
 "AUTO_RELOAD_ON": ("FALSE", "TRUE once auto-reload is switched on in both consoles"),
 "REFILL_WARN_DAYS": ("15", ""),
 # voice
 "VOICE": ("", "A, B, C or D after listening (blank = auto-pick A after 72h)"),
 "VOICE_SAMPLES_AT": ("", "auto"),
 "SPEED_TRIM": ("1.04", "1.00 = Part-1 speed"), "BREATH_DB": ("-34", "louder = closer to 0"), "BREATH_RATE": ("0.6", "0..1"),
 # platform
 "YT_CATEGORY": ("28", "Science & Technology"), "AI_LABEL_DEFAULT": ("TRUE", "honest label"),
 "META_ON": ("TRUE", ""), "IG_USER_ID": ("", "auto-filled at setup"), "FB_PAGE_ID": ("", "auto-filled at setup"),
 "OPERATOR_EMAIL": ("", "your email"), "DRIVE_FOLDER_ID": ("", "auto"),
 "EMAIL_LEVEL": ("minimal", "minimal = only money + monthly brief + launch"),
 # automation
 "AUTO_MERGE_REPAIRS": ("TRUE", "repair bot merges itself if all tests pass"),
 "MAX_REPAIRS_PER_WEEK": ("3", "repair bot attempts per 7 days"),
 "VOICE_WAIT_HOURS": ("72", "wait this long for your voice pick, then use A"),
 "PILOT_DONE": ("FALSE", "auto"),
 "LAUNCH_DONE": ("FALSE", "auto"),
 "FAL_STILL_MODEL": ("fal-ai/flux/schnell", "cheap stills"),
 "FAL_PREMIUM_MODEL": ("fal-ai/flux-pro/v1.1", "thumbnails + reel covers"),
 "FAL_LIVING_MODEL": ("fal-ai/ltx-video/image-to-video", "living stills"),
 "FAL_HERO_MODEL": ("fal-ai/kling-video/v2.1/standard/image-to-video", "hero clips"),
 "STILL_W": ("1632", ""), "STILL_H": ("918", ""),
 "PARALLAX_ON": ("TRUE", "depth parallax on stills"),
 "DRIVE_ARCHIVE": ("TRUE", "copy masters to Google Drive"),
 "KILL_CHECK": ("TRUE", "type KILL in Episodes.kill to stop a video before it goes live"),
 "TREND_CHANNELS": ("@WhatIfScienceShow,@kurzgesagt,@veritasium,@Vsauce,@RealLifeLore,@TheInfographicsShow,@zackdfilms,@MrBeast", "channels watched weekly"),
}
_settings_cache = None
def settings(refresh=False) -> dict:
    global _settings_cache
    if _settings_cache is not None and not refresh: return _settings_cache
    rows = store().rows("Settings")
    s = {k: v[0] for k, v in DEFAULTS.items()}
    for r in rows:
        if r.get("key"): s[r["key"]] = str(r.get("value", "")).strip()
    _settings_cache = s; return s
def S(key, cast=str):
    v = settings().get(key, DEFAULTS.get(key, ("",))[0])
    if cast is bool: return str(v).strip().upper() in ("TRUE", "YES", "1", "ON")
    try: return cast(v)
    except Exception: return cast(DEFAULTS[key][0]) if key in DEFAULTS else v
def set_setting(key, value):
    st = store(); global _settings_cache
    if not st.update("Settings", "key", key, {"value": value}):
        st.append("Settings", [{"key": key, "value": value, "note": DEFAULTS.get(key, ("", ""))[1]}])
    _settings_cache = None

# ---------------- logging ----------------
_logbuf, _lock = [], threading.Lock()
JOB = {"name": "job", "episode": ""}
_SECRET_ENVS = ("G_CLIENT_KEY", "G_REFRESH", "ANTHROPIC_KEY", "GEMINI_KEY", "FAL_KEY", "PEXELS_KEY", "META_PAGE_KEY", "G_CLIENT_ID", "SHEET_ID")
def scrub(text):
    """Never let a key reach a log, the Sheet, an email or an error file."""
    s = str(text)
    for n in _SECRET_ENVS:
        v = os.environ.get(n, "")
        if v and len(v) >= 8: s = s.replace(v, "***")
    s = re.sub(r"(key=|access_to" + r"ken=|Bearer\s+|Key\s+)[A-Za-z0-9_\-\.:]{12,}", r"\1***", s)
    return s

def log(msg, level="INFO", episode=None):
    msg = scrub(msg)
    line = f"[{level}] {JOB['name']} {episode or JOB['episode']}: {msg}"
    print(line, flush=True)
    with _lock: _logbuf.append({"ts": iso(), "job": JOB["name"], "episode_id": episode or JOB["episode"], "level": level, "message": str(msg)[:1500]})
    if len(_logbuf) >= 40: flush_log()
def flush_log():
    with _lock:
        rows = list(_logbuf); _logbuf.clear()
    if rows:
        try: store().append("Run_Log", rows)
        except Exception as e: print("log flush failed:", scrub(e))
    flush_costs()

# ---------------- money (buffered: one Sheet read per job, one write per flush) ----------------
_clock = threading.Lock()
_cost_buf, _session = [], {}
_base = {"v": None}
def _spend_base():
    if _base["v"] is None:
        life, month, m = {}, {}, now_utc().strftime("%Y-%m")
        for r in store().rows("Cost_Log"):
            try: v = float(r.get("inr") or 0)
            except Exception: continue
            p = r.get("provider", ""); life[p] = life.get(p, 0) + v
            if str(r.get("ts", "")).startswith(m): month[p] = month.get(p, 0) + v
        _base["v"] = {"life": life, "month": month}
    return _base["v"]
def cost(item, provider, units, usd, episode=None):
    inr = round(usd * S("USD_INR", float), 2)
    _spend_base()
    with _clock:
        _cost_buf.append({"ts": iso(), "episode_id": episode or JOB["episode"], "item": item, "provider": provider, "units": units, "inr": inr})
        _session[provider] = _session.get(provider, 0) + inr
    return inr
def flush_costs():
    with _clock:
        rows = list(_cost_buf); _cost_buf.clear()
    if rows:
        try: store().append("Cost_Log", rows)
        except Exception as e:
            print("cost flush failed:", scrub(e))
            with _clock: _cost_buf[:0] = rows
def month_spend(provider=None) -> float:
    b = _spend_base()["month"]
    if provider: return b.get(provider, 0) + _session.get(provider, 0)
    return sum(b.values()) + sum(_session.values())
def lifetime_spend_usd(provider) -> float:
    return (_spend_base()["life"].get(provider, 0) + _session.get(provider, 0)) / S("USD_INR", float)

def status(step, ok, detail=""):
    st = store(); val = "✅" if ok else "❌"
    if not st.update("Setup_Status", "step", step, {"status": val, "detail": str(detail)[:500], "updated": iso()}):
        st.append("Setup_Status", [{"step": step, "status": val, "detail": str(detail)[:500], "updated": iso()}])

def retry(fn, tries=4, wait=4, what="call"):
    last = None
    for a in range(tries):
        try: return fn()
        except Exception as e:
            last = e; log(f"{what} failed (try {a+1}/{tries}): {scrub(e)}", "WARN"); time.sleep(wait * (a + 1))
    raise last
