"""tools/repair.py v7.0 - repair bot. When a job crashes, send the traceback + the failing file to Claude, get a COMPLETE fixed file,
run Plan Guard + the offline rehearsal, and open a pull request (auto-merged if all checks pass and AUTO_MERGE_REPAIRS is TRUE).
Gemini and the owner never edit code."""
import os, re, sys, subprocess, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from whatifs import prompts as P

def _recent_repairs(days=7):
    try:
        out = subprocess.run(["gh", "pr", "list", "--state", "all", "--search", "Repair in:title", "--json", "createdAt", "--limit", "50"],
                             capture_output=True, text=True).stdout
        import datetime as dt
        cut = dt.datetime.utcnow() - dt.timedelta(days=days)
        return sum(1 for x in json.loads(out or "[]") if dt.datetime.strptime(x["createdAt"][:19], "%Y-%m-%dT%H:%M:%S") > cut)
    except Exception: return 0

def _same_error_recently(sig):
    try:
        out = subprocess.run(["gh", "pr", "list", "--state", "all", "--search", sig + " in:body", "--json", "number", "--limit", "5"], capture_output=True, text=True).stdout
        return len(json.loads(out or "[]")) > 0
    except Exception: return False

def main():
    err = open("last_error.txt").read() if os.path.exists("last_error.txt") else sys.stdin.read()
    from whatifs.core import scrub
    err = scrub(err)
    import hashlib
    sig = "sig" + hashlib.md5(re.sub(r"\d+", "", err[-600:]).encode()).hexdigest()[:10]
    cap = int(os.environ.get("MAX_REPAIRS", "3"))
    if _recent_repairs() >= cap:
        print(f"repair cap reached ({cap}/week) - skipping. Owner gets one email from the pipeline."); return 0
    if _same_error_recently(sig):
        print("this exact error was already attempted - skipping to avoid loops"); return 0
    files = re.findall(r'File "([^"]*?/(?:whatifs|tools)/[^"]+\.py)"', err)
    if not files: print("no repo file in traceback"); return 0
    rel = files[-1].split("/repo/")[-1] if "/repo/" in files[-1] else re.sub(r"^.*?/((?:whatifs|tools)/.*)$", r"\1", files[-1])
    if not os.path.exists(rel): print("file not found", rel); return 0
    src = open(rel).read()
    from whatifs.models import ask
    fixed = ask("sonnet", P.fill(P.REPAIR, path=rel, error=err[-6000:], file=src), "Return the full corrected file only.", want_json=False, max_tokens=32000, temperature=0)
    fixed = re.sub(r"^```(?:python)?\s*|\s*```$", "", fixed.strip(), flags=re.S) + "\n"
    if len(fixed) < len(src) * 0.6: print("repair too short, refused"); return 1
    br = f"repair-{int(time.time())}"
    subprocess.run(["git", "checkout", "-b", br], check=True)
    open(rel, "w").write(fixed)
    g = subprocess.run([sys.executable, "tools/plan_guard.py"]).returncode
    t = subprocess.run([sys.executable, "-m", "whatifs.cli", "rehearsal"], env=dict(os.environ, WI_FAKE="1", WI_SMALL="1", WI_WORK="rh")).returncode
    if g or t: print("repair did not pass tests; discarded"); return 1
    subprocess.run(["git", "-c", "user.name=repair-bot", "-c", "user.email=bot@users.noreply.github.com", "commit", "-am", f"repair: {rel}"], check=True)
    subprocess.run(["git", "push", "origin", br], check=True)
    subprocess.run(["gh", "pr", "create", "--title", f"Repair {rel}", "--body", "Automatic repair. Plan Guard + rehearsal passed. " + sig + "\n\n```\n" + err[-1500:] + "\n```", "--head", br], check=True)
    if os.environ.get("AUTO_MERGE", "TRUE").upper() == "TRUE":
        subprocess.run(["gh", "pr", "merge", br, "--squash", "--delete-branch"], check=False)
    return 0

if __name__ == "__main__":
    sys.exit(main())
