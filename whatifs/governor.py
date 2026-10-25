"""whatifs/governor.py v7.0 - monthly cap = max(floor, 10% of money actually received last month), max 25,000.
Near the cap: drop Kling, then living stills, then Opus. Publishing never stops."""
import datetime as dt
from whatifs.core import S, store, month_spend, lifetime_spend_usd, now_utc

def cap_inr():
    last = (now_utc().replace(day=1) - dt.timedelta(days=1)).strftime("%Y-%m")
    rec = 0.0
    for r in store().rows("Revenue_Log"):
        if str(r.get("month", "")).startswith(last):
            try: rec += float(r.get("inr_received") or 0)
            except Exception: pass
    return min(S("BUDGET_CEILING_INR", float), max(S("BUDGET_FLOOR_INR", float), rec * S("REVENUE_SHARE", float)))

def remaining_inr(): return cap_inr() - month_spend()

def episodes_left_this_month():
    from zoneinfo import ZoneInfo
    days = [d.strip()[:3] for d in S("PUBLISH_DAYS").split(",")]
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    today = now_utc().astimezone(ZoneInfo("America/New_York")).date(); n = 0; d = today
    while d.month == today.month:
        if names[d.weekday()] in days: n += 1
        d += dt.timedelta(days=1)
    return max(1, n)

def plan_for_episode(est_full_inr, eps_left):
    """Return what this episode may buy. est_full_inr = cost with everything on."""
    rem = remaining_inr(); per = rem / max(1, eps_left)
    p = {"kling": S("KLING_CLIPS", int), "living": S("LIVING_STILLS", int), "opus": True, "reason": "full"}
    if per >= est_full_inr: return p
    p["kling"] = 1; p["reason"] = "budget: 1 Kling"
    if per >= est_full_inr - 2 * S("PRICE_KLING_USD", float) * S("USD_INR", float): return p
    p["kling"] = 0; p["reason"] = "budget: no Kling"
    if per >= est_full_inr * 0.45: return p
    p["living"] = 2; p["opus"] = False; p["reason"] = "budget: minimum"
    return p

def _balance(provider):
    funded = S("FAL_FUNDED_USD" if provider == "fal" else "ANTHROPIC_FUNDED_USD", float)
    return funded - lifetime_spend_usd(provider)
def fal_allowed(): return S("AUTO_RELOAD_ON", bool) or _balance("fal") > 0.4
def claude_allowed(): return S("AUTO_RELOAD_ON", bool) or _balance("anthropic") > 0.4
def opus_allowed(): return claude_allowed() and remaining_inr() > 150

def runway_days(provider):
    usd = lifetime_spend_usd(provider)
    rows = [r for r in store().rows("Cost_Log") if r.get("provider") == provider]
    if not rows: return 999
    first = min(str(r["ts"]) for r in rows)
    try: days = max(1.0, (now_utc() - dt.datetime.strptime(first, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)).days or 1)
    except Exception: days = 30
    per_day = usd / days
    return 999 if per_day <= 0 else _balance(provider) / per_day
