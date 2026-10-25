"""whatifs/fakes.py v7.0 - offline stand-ins for every model call (rehearsal mode WI_FAKE=1). Zero cost."""
import json, re, random
from whatifs.core import SMALL

def _lines(n):
    pool = ["[calm] Right now, about eight billion people are doing something ordinary.", "[tension] But at exactly noon, all of them do it at once.",
            "[reveal] That adds up to a number nobody has ever written down.", "[aside] And somewhere, someone still replies 'k' to a long text... [beat] classic.",
            "[tension] The first ten seconds look harmless.", "[calm] Then the water starts to change colour.", "[pause:short]",
            "[reveal] By the end of the hour, the coastline has moved.", "[tension] And the strangest part is what happens to you.", "[callback] So next time, maybe just... don't."]
    return [pool[i % len(pool)] for i in range(n)]

def fake_reply(key, prompt):
    r = random.Random(len(prompt))
    if key == "scout":
        return json.dumps({"pitches": [{"premise": f"What if every pillow on Earth floated up at noon {i}?", "ptype": "collective",
            "headline": f"Pillows Left Earth {i}", "family": ["F08_rules", "F01_body", "F06_nature", "F09_space"][i], "triggers": ["self-relevance"],
            "scores": {k: 8 for k in ["grasp", "weird", "personal", "unpredictable", "fresh", "showable", "pull"]}, "unexpected_answer": "x", "why_now": "y"} for i in range(4)]})
    if key == "showrunner":
        return json.dumps({"premise": "What if every pillow on Earth floated up at noon?", "headline": "Every Pillow Just Left Earth", "family": "F08_rules", "ptype": "collective", "logline": "l", "thesis": "t",
            "unexpected_answer": "u", "emotional_arc": "a", "peak_moment": "p", "humour_plan": "h", "title_candidates": ["What If Every Pillow Floated Away?"],
            "thumb_concept": "c", "reel_hooks": ["a", "b"], "risks": "r"})
    if key == "memo": return json.dumps({"big_idea": "b", "needs": "n", "risk": "r", "techniques": ["Spielberg ripple"]})
    if key == "bible":
        return json.dumps({"conflicts": [{"issue": "i", "decision": "d"}], "beats": [{"n": i, "purpose": "p", "feeling": "f", "visual_world": "v", "sound": "s", "key_line": "k"} for i in range(1, 7)],
            "look": "cinematic, deep teal shadows, single warm key light, 35mm, fine grain", "recurring_motif": "m", "subscribe_moment": "If your pillow is still here, hit subscribe."})
    if key == "writer":
        m = re.search(r"~(\d+) words", prompt); words = int(m.group(1)) if m else 300
        n = max(10, words // 11) if not SMALL else 12
        body = []
        for b, chunk in enumerate([_lines(n)[i:i + 4] for i in range(0, n, 4)], 1):
            body.append(f"## BEAT {b}"); body += chunk
        return json.dumps({"title_working": "Pillows", "script": "\n".join(body), "facts": [{"claim": "c", "reasoning": "r"}]})
    if key == "critic":
        return json.dumps({"scores": {k: 8 for k in ["hook_strength", "curiosity_gap", "escalation", "unpredictable_answer", "science_plausible", "pacing_variety",
            "humour_cringe_free", "originality_vs_recent", "policy_safe", "title_thumb_promise_kept", "sounds_human", "psychological_pull"]}, "verdict": "PASS", "fixes": {}})
    if key == "director":
        m = re.search(r"There are (\d+) shots", prompt); n = int(m.group(1)) if m else 10
        mm = re.search(r"\n(\d+): ", prompt); off = int(mm.group(1)) if mm else 0
        types = ["still", "graphic", "stock", "still", "living", "still", "kling"]
        shots = []
        for i in range(n):
            t = types[i % len(types)]
            shots.append({"unit": off + i, "type": t, "prompt": f"A floating pillow over a city, shot {i}", "motion": "slow push in", "search": "ocean waves",
                          "graphic": {"label": "Pillows airborne", "from": 0, "to": 8000000000, "unit": ""}})
        return json.dumps({"shots": shots})
    if key == "packager":
        return json.dumps({"titles": ["What If Every Pillow Floated Away At Once?"], "thumb_text": "WHERE'D IT GO?", "thumb_prompt": "giant pillow over New York at dusk",
            "reel_cover_prompts": ["pillow storm vertical", "pillow over ocean vertical"], "reel_cover_texts": ["8 BILLION PILLOWS?", "LOOK UP"],
            "description": "What happens if every pillow on Earth floats away at once?\n\nChapters\n\n#science #whatif #space",
            "tags": ["what if", "science"], "pinned_comment": "Would you chase yours?"})
    if key == "reel":
        return json.dumps({"reels": [{"format": "R1_climax_why", "hook_text": "WAIT FOR IT", "shots": [6, 0, 1, 3, 4, 5], "lines": ["[tension] Every pillow on Earth just left.", "[reveal] And that's the good news."],
            "end_line": "Full video on our channel.", "caption": "Where would yours go? #whatif #science #shorts"},
            {"format": "R3_myth", "hook_text": "YOU'RE WRONG", "shots": [2, 3, 5, 6, 0], "lines": ["[calm] Most people think nothing happens.", "[tension] They're wrong."],
            "end_line": "Full video on our channel.", "caption": "Think again. #whatif #science #shorts"}]})
    if key == "sync": return json.dumps({"ok": True, "problems": []})
    if key == "humanize":
        m = re.search(r"NARRATION:\n(.*)\nReturn JSON", prompt, re.S)
        return json.dumps({"script": m.group(1) if m else "## BEAT 1\n[calm] Hello.", "changes": "rhythm"})
    if key == "research":
        return json.dumps({"exploding": [{"title": "t", "channel": "c", "why": "w", "patterns": {"title": "number", "thumb": "one object", "hook": "you", "structure": "countdown", "length": "9m", "humour": "light"}}],
            "platform_changes": [], "rising_angles": ["everyday x everyone"], "rules_for_room": ["Use a specific number in the title."]})
    if key == "strategy": return json.dumps({"name": "new_idea_" + str(r.randint(1, 999)), "definition": "A fresh structure."})
    if key == "brief": return "Monthly brief (rehearsal)."
    return json.dumps({"ok": True})
