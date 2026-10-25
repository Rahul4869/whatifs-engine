"""whatifs/cli.py v7.0 - entry point for every GitHub workflow.  python -m whatifs.cli <command>"""
import sys, os, json, traceback
from whatifs.core import JOB, log, flush_log, store, FAKE

def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "tick"
    JOB["name"] = cmd
    try:
        if cmd == "setup":
            from whatifs.manage import setup; setup()
        elif cmd == "voices":
            from whatifs.voice_lab import main as vl; vl()
        elif cmd == "tick":
            from whatifs.manage import tick
            a = tick(); print("ACTION", json.dumps(a))
            open(os.environ.get("GITHUB_OUTPUT", "/dev/null"), "a").write(f"action={a['action']}\nslot={a.get('slot','')}\nepisode={a.get('episode','')}\n")
        elif cmd == "produce":
            from whatifs.episode import produce
            slot = sys.argv[2]; print(json.dumps(produce(slot), default=str))
        elif cmd in ("release1", "release2"):
            from whatifs.manage import release; release(sys.argv[2], cmd)
        elif cmd == "trends":
            from whatifs.manage import trend_scout; trend_scout()
        elif cmd == "learn":
            from whatifs.manage import learn, money_check; learn(); money_check()
        elif cmd == "brief":
            from whatifs.manage import monthly_brief; monthly_brief()
        elif cmd == "models":
            from whatifs.models import discover_models; print(discover_models())
        elif cmd == "rehearsal":
            from tools.rehearsal import run; run()
        else:
            raise SystemExit(f"unknown command {cmd}")
    except Exception as e:
        log(f"{cmd} crashed: {e}\n{traceback.format_exc()[-2500:]}", "ERROR")
        from whatifs.core import scrub
        open("last_error.txt", "w").write(scrub(traceback.format_exc()))
        flush_log(); raise
    flush_log()

if __name__ == "__main__":
    main()
