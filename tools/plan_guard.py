"""
tools/plan_guard.py  v6.1.0
Runs on every GitHub save. RED = something broke the locked plan (Kernel). Operator only reports GREEN/RED.
"""
import ast, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SELF = os.path.abspath(__file__)
J = "".join  # patterns are assembled so this file never matches itself
RULES = [
    (J([r"claude-", r"(?:3|4|5|opus|sonnet|haiku)"]), "K8: model name typed in code (must come from Models tab)"),
    (J([r"gemini-", r"\d"]),                          "K8: model name typed in code (must come from Models tab)"),
    (J([r"v1\.1-", r"ultra"]),                        "K21: banned expensive image model"),
    (J([r"edge", r"[-_]tts"]),                        "K12: banned voice engine (Kokoro blend only)"),
    (J([r"critic_verdict\s*[:=]\s*[\"']", r"APPROVED"]), "K10: faked critic verdict"),
    (J([r"runtime_min\s*[:=]\s*", r"\d"]),            "K16: fixed runtime (must be sampled)"),
    (J([r"tbl", r"end"]),                             "K30: frame blending / watermark tampering"),
    (J([r"c2pa", r".{0,20}(strip|remove|erase)"]),    "K30: provenance stripping"),
    (J([r"map_metadata\s+", r"-1"]),                  "K30: metadata wiping"),
]
BANNED_NAME_WORDS = ["payment", "card", "billing", "password", "secret", "token", "bank", "transfer", "pwc"]
SCAN_EXT = (".py", ".yml", ".yaml", ".gs", ".js", ".json")

def main() -> int:
    bad = []
    for dp, dn, fn in os.walk(ROOT):
        dn[:] = [d for d in dn if d not in (".git", "__pycache__", "node_modules", ".venv")]
        for f in fn:
            p = os.path.join(dp, f); rel = os.path.relpath(p, ROOT)
            low = rel.lower()
            for wd in BANNED_NAME_WORDS:
                if wd in low: bad.append(f"{rel}: file name contains a flagged word ('{wd}')")
            if os.path.abspath(p) == SELF or not f.endswith(SCAN_EXT): continue
            txt = open(p, encoding="utf-8", errors="ignore").read()
            for pat, why in RULES:
                for m in re.finditer(pat, txt, re.I):
                    ln = txt[:m.start()].count("\n") + 1
                    bad.append(f"{rel}:{ln}: {why}")
            if f.endswith(".py"):
                try:
                    tree = ast.parse(txt); seen = set()
                    for node in tree.body:
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                            if node.name in seen: bad.append(f"{rel}:{node.lineno}: duplicate definition '{node.name}'")
                            seen.add(node.name)
                except SyntaxError as e:
                    bad.append(f"{rel}:{e.lineno}: Python syntax error")
    if bad:
        print("PLAN GUARD: RED"); [print("  -", b) for b in bad]; return 1
    print("PLAN GUARD: GREEN"); return 0

if __name__ == "__main__":
    sys.exit(main())
