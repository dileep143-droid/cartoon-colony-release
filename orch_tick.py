# 19 Nov 2026 owner: run the Mahabharatam episode pipeline from GitHub instead of the laptop.
# One "tick" (every 10 min, workflow orch_tick.yml): read the queue state from R2, move every episode ONE step forward, save, exit.
#   lip   -> lip-sync segments on the episode's language accounts (one GPU job per account), a segment is done when R2 seg/seg_N_lip.mp4
#            is newer than the episode's "since"; failed segment -> retried once. Faces + shot lists of finished segments are kept in R2 faces/.
#   mux   -> final join on account 15 (CPU)          ship -> R2 master -> Google Drive (size checked), link saved in state + links.json
#   clean -> delete that episode's notebooks on every account (only names starting with "<id>-")          done
# Each episode's build files arrive from the laptop as R2 s2work/orch/bundles/<id>.tar (orch_add.py). Nothing private is printed:
# no tokens, no links, no account names - only episode ids, phases, segment numbers and account numbers.
import os, sys, io, json, time, re, tarfile, tempfile, subprocess, urllib.request, shutil
from concurrent.futures import ThreadPoolExecutor
import boto3
from botocore.config import Config
HERE = os.path.dirname(os.path.abspath(__file__)); WORK = tempfile.mkdtemp(prefix="orch_")
BUCKET = "eduorbex-media"; SKEY = "s2work/orch/state.json"; LKEY = "s2work/orch/links.json"
S3 = boto3.client("s3", endpoint_url=os.environ["CF_R2_ENDPOINT"], aws_access_key_id=os.environ["CF_R2_ACCESS_KEY_ID"],
                  aws_secret_access_key=os.environ["CF_R2_SECRET_ACCESS_KEY"], region_name="auto", config=Config(signature_version="s3v4"))
T_START = time.time(); BUDGET = float(os.environ.get("TICK_MINUTES", "25")) * 60
def log(*a): print(time.strftime("%H:%M:%S"), *a, flush=True)

# ---------- Kaggle (tokens from secrets KAGGLE_KEYn; output never printed) ----------
sys.path.insert(0, HERE)
from orch_kaggle import kaggle, user_of, kstate, kstate2, kernels_of, busy
# a dispatch.py the bundled build helpers (jobs.py) can import
open(os.path.join(WORK, "dispatch.py"), "w").write(
    "import sys; sys.path.insert(0, %r)\nfrom orch_kaggle import kaggle, user_of\nE = {}\n" % HERE)

# ---------- R2 ----------
def r2_json(key, default):
    try: return json.loads(S3.get_object(Bucket=BUCKET, Key=key)["Body"].read())
    except Exception: return default
def r2_put_json(key, obj): S3.put_object(Bucket=BUCKET, Key=key, Body=json.dumps(obj, indent=1, ensure_ascii=False).encode())
def r2_mtime(key):
    try: return S3.head_object(Bucket=BUCKET, Key=key)["LastModified"].timestamp()
    except Exception: return 0
def r2_size(key):
    try: return S3.head_object(Bucket=BUCKET, Key=key)["ContentLength"]
    except Exception: return 0

# ---------- one episode's build folder ----------
def build_dir(ep):
    d = os.path.join(WORK, ep["id"])
    if not os.path.isdir(d):
        os.makedirs(d); body = S3.get_object(Bucket=BUCKET, Key=f"s2work/orch/bundles/{ep['id']}.tar")["Body"].read()
        tarfile.open(fileobj=io.BytesIO(body)).extractall(d)
        envf = os.path.join(WORK, "r2.env")
        with open(envf, "w") as f:
            for k in ("CF_R2_ENDPOINT", "CF_R2_ACCESS_KEY_ID", "CF_R2_SECRET_ACCESS_KEY"): f.write(f"{k}={os.environ[k]}\n")
        j = open(os.path.join(d, "jobs.py"), encoding="utf-8").read()
        j = re.sub(r'sys\.path\.insert\(0, r"[^"]*kaggle\\multi"\)', f"sys.path.insert(0, {WORK!r})", j)
        j = re.sub(r'open\(r"[^"]*\.env", encoding=\'utf-8-sig\'\)', f"open({envf!r}, encoding='utf-8-sig')", j)
        open(os.path.join(d, "jobs.py"), "w", encoding="utf-8").write(j)
    return d
def run_py(ep, *args):
    d = build_dir(ep)
    r = subprocess.run([sys.executable, *args], cwd=d, capture_output=True, text=True, env=dict(os.environ, PYTHONPATH=WORK + os.pathsep + d))
    return r.returncode, (r.stdout + r.stderr)[-400:]
def nsegs(ep): return len(json.load(open(os.path.join(build_dir(ep), "plan.json"), encoding="utf-8"))["segs_lip"])

# ---------- phases ----------
def step_lip(ep, keys, free_keys):
    pre = ep["pre"]; ns = nsegs(ep); L = ep.setdefault("launched", {}); tries = ep.setdefault("tries", {})
    done = {s for s in range(ns) if r2_mtime(f"{pre}seg/seg_{s}_lip.mp4") > ep["since"]}
    for s, (k, kid) in list(L.items()):                       # finished or failed?
        s = int(s)
        if s in done:
            if not ep.setdefault("faces", {}).get(str(s)):        # keep face + shot list for the Shorts
                o = os.path.join(WORK, "out", f"{ep['id']}_{s}"); os.makedirs(o, exist_ok=True)
                kaggle(k, "kernels", "output", kid, "-p", o, "--file-pattern", r"(face_full_.*\.mp4|shots_.*\.json)", timeout=600)
                for fn in os.listdir(o): S3.upload_file(os.path.join(o, fn), BUCKET, f"{pre}faces/{fn}")
                ep["faces"][str(s)] = 1
            del L[str(s)]; log(ep["id"], "seg", s, "done (key", k, ")"); continue
        st = kstate(k, kid)
        if st == "run": continue
        del L[str(s)]
        if tries.get(str(s), 0) >= 2: ep["phase"] = "failed"; ep["why"] = f"segment {s} failed twice"; log(ep["id"], "seg", s, "FAILED twice"); return
        log(ep["id"], "seg", s, st, "on key", k, "-> again")
    todo = [s for s in range(ns) if s not in done and str(s) not in L]
    for k in keys:
        if not todo: break
        if k not in free_keys: continue
        s = todo.pop(0); tries[str(s)] = tries.get(str(s), 0) + 1; free_keys.discard(k)
        kid = f"{user_of(k)}/{ep['id']}-seg-{s}-lip"; kaggle(k, "kernels", "delete", kid, "-y")
        rc, out = run_py(ep, "run_seg.py", str(k), str(s), "lip")
        if rc != 0 or "pushed" not in out: log(ep["id"], "seg", s, "push failed on key", k); tries[str(s)] -= 1; continue
        L[str(s)] = [k, kid]; log(ep["id"], "seg", s, "-> key", k)
    if len(done) == ns: ep["phase"] = "mux"; log(ep["id"], "all", ns, "segments done -> join")
    else: log(ep["id"], "segments done", len(done), "of", ns, "| running", sorted(int(x) for x in L))
def step_mux(ep):
    pre = ep["pre"]; ns = nsegs(ep); m = ep.setdefault("mux", {})
    if r2_mtime(f"{pre}ship/{ep['master']}") > ep["since"] and (not m or kstate(15, m["kid"]) != "run"):
        ep["phase"] = "ship"; log(ep["id"], "join done -> Drive"); return
    if m:
        st = kstate(15, m["kid"])
        if st == "run": log(ep["id"], "join running"); return
        if m.get("tries", 1) >= 2: ep["phase"] = "failed"; ep["why"] = "join failed twice"; log(ep["id"], "join FAILED twice"); return
        log(ep["id"], "join", st, "-> again")
    rc, out = run_py(ep, "run_mux.py", "15", "main", ",".join(f"{i}_lip" for i in range(ns)))
    if "pushed" in out: ep["mux"] = {"kid": f"{user_of(15)}/{ep['id']}-mux-main", "tries": m.get("tries", 0) + 1}; log(ep["id"], "join pushed (key 15)")
    else: log(ep["id"], "join push failed")
def drive():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    c = Credentials.from_authorized_user_info(json.loads(os.environ["DRIVE_TOKEN"]))
    if not c.valid: c.refresh(Request())
    return build("drive", "v3", credentials=c, cache_discovery=False)
def drive_folder(dr, path):
    pid = None
    for nm in path:
        q = f"name='{nm}' and mimeType='application/vnd.google-apps.folder' and trashed=false" + (f" and '{pid}' in parents" if pid else " and 'root' in parents")
        f = dr.files().list(q=q, fields="files(id)").execute().get("files", [])
        pid = f[0]["id"] if f else dr.files().create(body={"name": nm, "mimeType": "application/vnd.google-apps.folder", **({"parents": [pid]} if pid else {})}, fields="id").execute()["id"]
    return pid
def step_ship(ep):
    from googleapiclient.http import MediaFileUpload
    key = f"{ep['pre']}ship/{ep['master']}"; size = r2_size(key); name = ep.get("drive_name") or ep["master"]
    dr = drive(); pid = drive_folder(dr, ["BuBu TV Archive", "R2"] + ep["pre"].strip("/").split("/") + ["ship"])
    have = [h for h in dr.files().list(q=f"name='{name}' and '{pid}' in parents and trashed=false", fields="files(id,size)").execute().get("files", []) if int(h.get("size", -1)) == size]
    if not have:
        tmp = os.path.join(WORK, "master.bin"); S3.download_file(BUCKET, key, tmp)
        if os.path.getsize(tmp) != size: log(ep["id"], "download incomplete, retry next tick"); return
        up = dr.files().create(body={"name": name, "parents": [pid]}, media_body=MediaFileUpload(tmp, chunksize=32 << 20, resumable=True), fields="id,size")
        resp = None
        while resp is None: _, resp = up.next_chunk()
        os.remove(tmp)
        if int(resp["size"]) != size: log(ep["id"], "Drive size mismatch, retry next tick"); return
        have = [resp]
    ep["link"] = f"https://drive.google.com/file/d/{have[0]['id']}/view"; ep["phase"] = "clean2" if ep.get("v") == 2 else "clean"
    links = r2_json(LKEY, {}); links[ep["id"]] = {"name": name, "link": ep["link"], "t": time.strftime("%Y-%m-%d %H:%M")}; r2_put_json(LKEY, links)
    log(ep["id"], "on Drive (", round(size / 1e6), "MB ) -> link saved in R2 links.json")
def step_clean(ep, all_keys):
    n = 0
    def one(k):
        c = 0
        for ref in kernels_of(k):
            if ref.split("/")[1].startswith(ep["id"] + "-") and kstate(k, ref) != "run":
                c += "deleted" in kaggle(k, "kernels", "delete", ref, "-y")[1]
        return c
    with ThreadPoolExecutor(8) as ex: n = sum(ex.map(one, all_keys))
    ep["phase"] = "done"; ep["cleaned"] = n; log(ep["id"], "notebooks deleted", n, "-> DONE")

# ---------- v2 (owner 23 Nov): Kaggle = lip-sync ONLY (lip_kernel.py), GitHub = all assembly (episode_assemble.yml) ----------
#   lip2     -> lip jobs on the shared pool st["keys2"] (one GPU job per account); a job is done when R2 faces/lipmeta_<j>.json is newer
#               than "since" (written last by the kernel, holds its measured seconds); a job QUEUED > 10 min gets a race copy <id>-lip-<j>b on
#               another free account, the first RUNNING copy is kept and the other deleted; a failed job is retried once
#   assemble -> dispatch episode_assemble.yml (matrix per segment + mux), wait for the master in R2 ship/; a failed run is retried once
#   ship     -> as v1 (Drive, size checked)        clean2 -> this episode's notebooks + R2 seg/ parts deleted (faces/ kept for the Shorts)
def lipjobs(ep):
    p = json.load(open(os.path.join(build_dir(ep), "plan.json"), encoding="utf-8"))
    return p.get("lipjobs") or [{"job": i} for i in range(len(p["segs_lip"]))]
def step_lip2(ep, keys, free_keys):
    pre = ep["pre"]; nj = len(lipjobs(ep)); L = ep.setdefault("launched", {}); tries = ep.setdefault("tries", {}); sec = ep.setdefault("lipsec", {})
    done = {j for j in range(nj) if r2_mtime(f"{pre}faces/lipmeta_{j}.json") > ep["since"]}
    for j in done:
        if str(j) not in sec:
            m = r2_json(f"{pre}faces/lipmeta_{j}.json", {}); sec[str(j)] = [m.get("total_s", 0), m.get("setup_s", 0), m.get("lip_s", 0), m.get("deepcache"), m.get("steps")]
    for j, copies in list(L.items()):
        if int(j) in done:
            for k, kid, _ in copies:
                if kstate(k, kid) == "run": kaggle(k, "kernels", "delete", kid, "-y")   # a race copy still going: not needed any more
            del L[j]; log(ep["id"], "lip job", j, "done (key", copies[0][0], ")"); continue
        sts = [(k, kid, t, kstate2(k, kid)) for k, kid, t in copies]
        run = [c for c in sts if c[3] == "running"]
        if run and len(sts) > 1:                                   # race won: keep the first RUNNING copy, delete the rest
            for c in sts:
                if c is not run[0]: kaggle(c[0], "kernels", "delete", c[1], "-y")
            L[j] = [list(run[0][:3])]; log(ep["id"], "lip job", j, "race won by key", run[0][0]); continue
        if any(c[3] in ("running", "queued") for c in sts):
            if not run and len(sts) < 2 and all(time.time() - c[2] > 600 for c in sts):
                k2 = next((k for k in keys if k in free_keys), None)
                if k2 is not None:
                    free_keys.discard(k2); kid2 = f"{user_of(k2)}/{ep['id']}-lip-{j}b"; kaggle(k2, "kernels", "delete", kid2, "-y")
                    rc, out = run_py(ep, "run_lip.py", str(k2), j, "b")
                    if rc == 0 and "pushed" in out: L[j].append([k2, kid2, time.time()]); log(ep["id"], "lip job", j, "queued > 10 min -> race copy on key", k2)
            continue
        del L[j]                                                    # finished without its lipmeta = failed
        if tries.get(j, 0) >= 2: ep["phase"] = "failed"; ep["why"] = f"lip job {j} failed twice"; log(ep["id"], "lip job", j, "FAILED twice"); return
        log(ep["id"], "lip job", j, "/".join(c[3] for c in sts), "-> again")
    todo = [j for j in range(nj) if j not in done and str(j) not in L]
    for k in keys:
        if not todo: break
        if k not in free_keys: continue
        j = todo.pop(0); free_keys.discard(k)
        kid = f"{user_of(k)}/{ep['id']}-lip-{j}"; kaggle(k, "kernels", "delete", kid, "-y")
        rc, out = run_py(ep, "run_lip.py", str(k), str(j))
        if rc != 0 or "pushed" not in out: log(ep["id"], "lip job", j, "push failed on key", k); todo.insert(0, j); continue
        tries[str(j)] = tries.get(str(j), 0) + 1; L[str(j)] = [[k, kid, time.time()]]; log(ep["id"], "lip job", j, "-> key", k)
    ep["kaggle_h"] = round(sum(v[0] for v in sec.values()) / 3600, 2)
    if len(done) == nj:
        ep["phase"] = "assemble"; ep["lip_done_t"] = time.time()
        log(ep["id"], "all", nj, "lip jobs done, Kaggle", ep["kaggle_h"], "h (sum of kernel run times) -> GitHub assembly")
    else: log(ep["id"], "lip jobs done", len(done), "of", nj, "| running", sorted(int(x) for x in L), "| Kaggle so far", ep["kaggle_h"], "h")
def gh_runs(wf):
    r = subprocess.run(["gh", "run", "list", "--workflow", wf, "--limit", "30", "--json", "displayTitle,status,conclusion,createdAt,databaseId"], capture_output=True, text=True, cwd=HERE)
    try: return json.loads(r.stdout)
    except Exception: return []
def step_assemble(ep):
    import calendar
    pre = ep["pre"]; a = ep.setdefault("asm", {})
    if r2_mtime(f"{pre}ship/{ep['master']}") > ep["since"]:
        a["done_t"] = time.time(); a["gh_min"] = round((a["done_t"] - a.get("t0", a["done_t"])) / 60, 1); ep["phase"] = "ship"
        log(ep["id"], "GitHub assembly done in", a["gh_min"], "min -> Drive"); return
    title = f"assemble {ep['id']}"
    runs = [r for r in gh_runs("episode_assemble.yml") if r["displayTitle"] == title and calendar.timegm(time.strptime(r["createdAt"], "%Y-%m-%dT%H:%M:%SZ")) >= a.get("t", 0) - 120]
    if a.get("t"):
        if runs and runs[0]["status"] != "completed": log(ep["id"], "assembly running"); return
        if not runs and time.time() - a["t"] < 900: log(ep["id"], "assembly dispatched, waiting for the run"); return
        if a.get("tries", 0) >= 2: ep["phase"] = "failed"; ep["why"] = "GitHub assembly failed twice"; log(ep["id"], "assembly FAILED twice"); return
        log(ep["id"], "assembly", runs[0]["conclusion"] if runs else "never started", "-> again")
    r = subprocess.run(["gh", "workflow", "run", "episode_assemble.yml", "--ref", "main", "-f", f"id={ep['id']}"], capture_output=True, text=True, cwd=HERE)
    if r.returncode == 0:
        a["t"] = time.time(); a.setdefault("t0", a["t"]); a["tries"] = a.get("tries", 0) + 1; log(ep["id"], "assembly dispatched (try", a["tries"], ")")
    else: log(ep["id"], "assembly dispatch failed")
def step_clean2(ep, all_keys):
    def one(k):
        c = 0
        for ref in kernels_of(k):
            if ref.split("/")[1].startswith(ep["id"] + "-") and kstate(k, ref) != "run":
                c += "deleted" in kaggle(k, "kernels", "delete", ref, "-y")[1]
        return c
    with ThreadPoolExecutor(8) as ex: n = sum(ex.map(one, all_keys))
    r2n = 0
    for pg in S3.get_paginator("list_objects_v2").paginate(Bucket=BUCKET, Prefix=f"{ep['pre']}seg/"):
        for o in pg.get("Contents", []):
            if "_gh." in o["Key"]: S3.delete_object(Bucket=BUCKET, Key=o["Key"]); r2n += 1
    links = r2_json(LKEY, {})
    if ep["id"] in links: links[ep["id"]].update({"kaggle_h": ep.get("kaggle_h"), "gh_min": ep.get("asm", {}).get("gh_min")}); r2_put_json(LKEY, links)
    ep["phase"] = "done"; ep["cleaned"] = n; log(ep["id"], "notebooks deleted", n, "| R2 segment parts deleted", r2n, "| faces kept for the Shorts -> DONE")

# ---------- main ----------
st = r2_json(SKEY, None)
if not st: log("no state yet"); sys.exit(3)
if st.get("paused"): log("paused"); sys.exit(3)
KEYS = {k: [int(x) for x in v] for k, v in st["keys"].items()}; ALL = sorted({k for v in KEYS.values() for k in v} | {15})
eps = [e for e in st["queue"] if e.get("phase") not in ("done", "failed")]
lip_now = {}
for e in eps:                                                 # one episode per language uses the GPUs at a time (queue order)
    if e["phase"] == "lip" and e["lang"] not in lip_now: lip_now[e["lang"]] = e
# v2 pool (owner 23 Nov): every working account, minus 2 (owner-voice RVC), 7 + 9 (no login), 16 (= account 15), 18 (no internet)
KEYS2 = [int(x) for x in st.get("keys2", [1, 3, 4, 5, 6, 8, 10, 11, 12, 13, 14, 15, 17, 19, 20, 21])]
ALL = sorted(set(ALL) | set(KEYS2))
v2_lip = [e for e in eps if e.get("v") == 2 and e["phase"] == "lip2"]
free = set()
if lip_now or v2_lip:
    need = sorted({k for l in lip_now for k in KEYS[l]} | (set(KEYS2) if v2_lip else set()))
    with ThreadPoolExecutor(8) as ex: free = {k for k, b in zip(need, ex.map(busy, need)) if not b}
for e in eps:
    if time.time() - T_START > BUDGET: log("time budget used, rest next tick"); break
    try:
        if e["phase"] == "lip" and lip_now.get(e["lang"]) is e: step_lip(e, KEYS[e["lang"]], free)
        elif e["phase"] == "mux": step_mux(e)
        elif e["phase"] == "ship": step_ship(e)
        elif e["phase"] == "clean": step_clean(e, ALL)
        elif e["phase"] == "lip2": step_lip2(e, KEYS2, free)          # v2 episodes share the pool in queue order
        elif e["phase"] == "assemble": step_assemble(e)
        elif e["phase"] == "clean2": step_clean2(e, ALL)
    except Exception as x:
        log(e["id"], "step error", type(x).__name__, str(x)[:120].replace(os.environ.get("CF_R2_ENDPOINT", "#"), "R2"))
    cur = r2_json(SKEY, st)                                   # keep episodes the laptop added while this tick ran (and a pause it set)
    have = {x["id"] for x in st["queue"]}; st["queue"] += [x for x in cur.get("queue", []) if x["id"] not in have]
    st["paused"] = cur.get("paused", False)
    r2_put_json(SKEY, st)                                     # save after every episode, so a crash loses nothing
log("tick done:", ", ".join(f"{e['id']}={e['phase']}" for e in st["queue"]))
sys.exit(0 if any(e.get("phase") not in ("done", "failed") for e in st["queue"]) else 3)   # 3 = nothing left to do
