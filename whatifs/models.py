"""whatifs/models.py v7.0 - model discovery (never typed in), Claude + Gemini calls, JSON repair, automatic fallback, fake mode."""
from __future__ import annotations
import json, re, time, concurrent.futures as cf
import requests
from whatifs.core import env, log, cost, S, store, iso, FAKE, status

ANTH = "https://api.anthropic.com/v1/"
GEM = "https://generativelanguage.googleapis.com/v1beta/"
def AH(): return {"x-api-key": env("ANTHROPIC_KEY"), "anthropic-version": "2023-06-01", "content-type": "application/json"}

def _vernum(s):
    return tuple(float(n) for n in re.findall(r"\d+(?:\.\d+)?", s)[:3]) or (0,)

def discover_models(write=True) -> dict:
    """Ask both providers which models exist today. Newest Opus, Sonnet, Gemini Pro and Flash are chosen."""
    chosen = {}
    if FAKE:
        chosen = {"opus": "fake-opus", "sonnet": "fake-sonnet", "gem_pro": "fake-pro", "gem_flash": "fake-flash"}
    else:
        try:
            r = requests.get(ANTH + "models?limit=100", headers=AH(), timeout=30); r.raise_for_status()
            data = sorted(r.json().get("data", []), key=lambda m: m.get("created_at", ""), reverse=True)
            for fam in ("opus", "sonnet"):
                for m in data:
                    if fam in m["id"]: chosen[fam] = m["id"]; break
        except Exception as e: log(f"Anthropic model list failed: {e}", "WARN")
        try:
            r = requests.get(GEM + "models?pageSize=200", headers={"x-goog-api-key": env("GEMINI_KEY")}, timeout=30); r.raise_for_status()
            ms = [m["name"].split("/")[-1] for m in r.json().get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
            bad = ("vision", "tts", "image", "embedding", "live", "audio", "lite", "exp", "preview", "thinking", "learnlm", "gemma")
            def pick(word):
                c = [m for m in ms if word in m and not any(b in m for b in bad)] or [m for m in ms if word in m and "lite" not in m]
                c.sort(key=_vernum, reverse=True); return c[0] if c else None
            chosen["gem_pro"] = pick("pro"); chosen["gem_flash"] = pick("flash")
        except Exception as e: log(f"Gemini model list failed: {e}", "WARN")
    if write:
        store().replace("Models", [{"role": k, "provider": "anthropic" if k in ("opus", "sonnet") else "google",
                                    "model": v, "chosen_at": iso()} for k, v in chosen.items() if v])
    return chosen

_models = None
def model(role):
    global _models
    if _models is None:
        _models = {r["role"]: r["model"] for r in store().rows("Models") if r.get("model")} or discover_models()
    return _models.get(role)

def parse_json(text):
    if isinstance(text, (dict, list)): return text
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", (text or "").strip(), flags=re.S).strip()
    cands = [t]
    if "{" in t: cands.append(t[t.find("{"): t.rfind("}") + 1])
    if "[" in t: cands.append(t[t.find("["): t.rfind("]") + 1])
    for c in cands:
        for x in (c, re.sub(r",\s*([}\]])", r"\1", c)):
            try: return json.loads(x)
            except Exception: pass
    raise ValueError("model did not return valid JSON: " + t[:300])

def _claude(role, system, prompt, max_tokens, temperature, search, episode):
    mid = model(role)
    if not mid: raise RuntimeError(f"no {role} model")
    body = {"model": mid, "max_tokens": max_tokens, "temperature": temperature,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": prompt}]}
    if search: body["tools"] = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 4}]
    r = requests.post(ANTH + "messages", headers=AH(), json=body, timeout=900)
    if r.status_code == 400 and "temperature" in r.text:
        body.pop("temperature"); r = requests.post(ANTH + "messages", headers=AH(), json=body, timeout=900)
    if r.status_code != 200: raise RuntimeError(f"Claude {r.status_code}: {r.text[:300]}")
    j = r.json(); u = j.get("usage", {})
    pin, pout = (S("PRICE_OPUS_IN", float), S("PRICE_OPUS_OUT", float)) if role == "opus" else (S("PRICE_SONNET_IN", float), S("PRICE_SONNET_OUT", float))
    usd = (u.get("input_tokens", 0) * pin + u.get("cache_creation_input_tokens", 0) * pin * 1.25 +
           u.get("cache_read_input_tokens", 0) * pin * 0.1 + u.get("output_tokens", 0) * pout) / 1e6
    usd += (u.get("server_tool_use") or {}).get("web_search_requests", 0) * 0.01
    cost(f"claude_{role}", "anthropic", u.get("output_tokens", 0), usd, episode)
    return "".join(b.get("text", "") for b in j.get("content", []) if b.get("type") == "text")

def _gemini(role, system, prompt, max_tokens, temperature, search, want_json):
    mid = model(role) or model("gem_flash")
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens}}
    if search: body["tools"] = [{"google_search": {}}]
    elif want_json: body["generationConfig"]["responseMimeType"] = "application/json"
    r = requests.post(GEM + f"models/{mid}:generateContent", headers={"x-goog-api-key": env("GEMINI_KEY")}, json=body, timeout=600)
    if r.status_code != 200: raise RuntimeError(f"Gemini {r.status_code}: {r.text[:300]}")
    c = (r.json().get("candidates") or [{}])[0]
    return "".join(p.get("text", "") for p in c.get("content", {}).get("parts", []))

CHAINS = {"opus": [("c", "opus"), ("c", "sonnet"), ("g", "gem_pro"), ("g", "gem_flash")],
          "sonnet": [("c", "sonnet"), ("c", "opus"), ("g", "gem_pro"), ("g", "gem_flash")],
          "critic": [("g", "gem_pro"), ("g", "gem_flash"), ("c", "sonnet")],
          "flash": [("g", "gem_flash"), ("g", "gem_pro"), ("c", "sonnet")],
          "research": [("g", "gem_pro"), ("g", "gem_flash"), ("c", "sonnet")]}

def ask(role, system, prompt, want_json=True, max_tokens=6000, temperature=0.8, search=False, episode=None, fake_key=None):
    """Never blocks: walks the fallback chain. Claude roles move to Gemini when Claude credit runs out."""
    if FAKE:
        from whatifs.fakes import fake_reply
        out = fake_reply(fake_key or role, prompt)
        return parse_json(out) if want_json else out
    from whatifs.governor import claude_allowed, opus_allowed
    chain = list(CHAINS[role])
    if role == "opus" and not opus_allowed(): chain = [x for x in chain if x[1] != "opus"]
    if not claude_allowed(): chain = [x for x in chain if x[0] == "g"] + [x for x in chain if x[0] == "c"]
    last = None
    for prov, r in chain:
        for attempt in range(2):
            try:
                txt = (_claude(r, system, prompt, max_tokens, temperature, search, episode) if prov == "c"
                       else _gemini(r, system, prompt, max_tokens, temperature, search, want_json))
                return parse_json(txt) if want_json else txt
            except Exception as e:
                last = e; log(f"{role} via {r} failed: {e}", "WARN", episode); time.sleep(3 + 5 * attempt)
    raise RuntimeError(f"all models failed for {role}: {last}")

def ask_many(jobs, workers=4):
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        return [f.result() for f in [ex.submit(ask, **j) for j in jobs]]

def selftest():
    m = discover_models()
    status("models_found", bool(m.get("sonnet") and m.get("gem_pro")), json.dumps(m))
    for name, fn in (("anthropic_works", lambda: _claude("sonnet", "Reply OK.", "OK?", 5, 0, False, "selftest")),
                     ("gemini_works", lambda: _gemini("gem_flash", "Reply {\"ok\":true}", "ping", 50, 0, False, True))):
        try: t = fn(); status(name, bool(t), t[:120])
        except Exception as e: status(name, False, str(e)[:300])
