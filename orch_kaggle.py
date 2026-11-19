# Kaggle helpers for orch_tick.py (tokens come from the KAGGLE_KEYn secrets; command output is never printed).
import os, subprocess
def kaggle(key, *args, timeout=180):
    env = dict(os.environ, KAGGLE_API_TOKEN=os.environ[f"KAGGLE_KEY{key}"], PYTHONUTF8="1")
    try:
        r = subprocess.run(["kaggle", *args], env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
        return r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired: return 1, "timeout"
_users = {}
def user_of(key):
    if key not in _users:
        _, out = kaggle(key, "config", "view")
        _users[key] = next((l.split(":", 1)[1].strip() for l in out.splitlines() if "username" in l.lower()), None)
    return _users[key]
def kstate(key, kid):
    s = kaggle(key, "kernels", "status", kid)[1]
    return "run" if ("RUNNING" in s or "QUEUED" in s) else "done" if "COMPLETE" in s else "err" if ("ERROR" in s or "CANCEL" in s) else "none"
def kernels_of(key):
    _, o = kaggle(key, "kernels", "list", "--mine", "--page-size", "100", "--csv")
    return [l.split(",")[0] for l in o.strip().splitlines()[1:] if "/" in l.split(",")[0]]
def busy(key):
    return any(kstate(key, ref) == "run" for ref in kernels_of(key))
