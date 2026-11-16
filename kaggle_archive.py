r"""Owner 16 Nov 2026: back up OLD Kaggle notebooks (code + metadata + outputs) to Google Drive (5 TB account), then delete them from Kaggle.
python kaggle_archive.py <key number> [cutoff date, default 2026-11-15]
- only notebooks whose last run is BEFORE the cutoff (current Mahabharatam jobs are never touched); ls-env is always kept
- one zip per notebook -> Drive "Kaggle_Notebooks_Archive_2026-11-16/<kaggle user>/<slug>.zip"
- a notebook is deleted only after Drive reports the same file size as the local zip"""
import csv, json, os, re, shutil, subprocess, sys, zipfile
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
key = sys.argv[1]; cutoff = sys.argv[2] if len(sys.argv) > 2 else "2026-11-15"
tok = os.environ.get("KAGGLE_ONE", "").strip()
if not tok: print("no KAGGLE_KEY%s secret - skip" % key); sys.exit(0)
env = dict(os.environ, KAGGLE_API_TOKEN=tok, PYTHONUTF8="1")
def kg(*a): r = subprocess.run(["kaggle", *a], env=env, capture_output=True, text=True); return r.returncode, r.stdout + r.stderr
rows = []
for page in range(1, 11):
    rc, out = kg("kernels", "list", "--mine", "--page-size", "100", "-p", str(page), "--csv")
    if rc: print("list failed:", out[-200:]); sys.exit(0)
    rr = [r for r in csv.reader(out.splitlines()[1:]) if len(r) >= 4 and re.fullmatch(r"[\w.-]+/[\w.-]+", r[0])]   # 16 Nov: titles with commas broke split(",")
    rows += rr
    if len(rr) < 100: break
todo = [r[0] for r in rows if r[3][:10] < cutoff and not re.search(r"/ls-env", r[0])]
print(f"key {key}: {len(rows)} notebooks, {len(todo)} older than {cutoff} to archive", flush=True)
if not todo: sys.exit(0)
c = Credentials.from_authorized_user_info(json.loads(os.environ["DRIVE_TOKEN_5TB"]))
if not c.valid: c.refresh(Request())
dr = build("drive", "v3", credentials=c, cache_discovery=False)
def folder(nm, parent=None):
    q = f"name='{nm}' and mimeType='application/vnd.google-apps.folder' and trashed=false" + (f" and '{parent}' in parents" if parent else "")
    f = dr.files().list(q=q, fields="files(id)").execute().get("files", [])
    return f[0]["id"] if f else dr.files().create(body={"name": nm, "mimeType": "application/vnd.google-apps.folder", **({"parents": [parent]} if parent else {})}, fields="id").execute()["id"]
user = todo[0].split("/")[0]; pid = folder(user, folder("Kaggle_Notebooks_Archive_2026-11-16"))
ok = fail = 0
for ref in todo:
    slug = ref.split("/")[1]; d = f"w/{slug}"; shutil.rmtree("w", ignore_errors=True); os.makedirs(d)
    r1, o1 = kg("kernels", "pull", ref, "-p", d, "-m"); r2, o2 = kg("kernels", "output", ref, "-p", f"{d}/output")
    open(f"{d}/_log.txt", "w").write(o1[-3000:] + "\n" + o2[-3000:])
    if r1 != 0: print("PULL FAILED, kept on Kaggle:", ref, o1[-120:].replace("\n", " "), flush=True); fail += 1; continue
    zp = f"{slug}.zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for root, _, fs in os.walk(d):
            for f in fs: z.write(os.path.join(root, f), os.path.relpath(os.path.join(root, f), "w"))
    size = os.path.getsize(zp)
    ex = dr.files().list(q=f"name='{zp}' and '{pid}' in parents and trashed=false", fields="files(id,size)").execute().get("files")
    if ex and int(ex[0].get("size", -1)) == size: got = int(ex[0]["size"])
    else:
        up = dr.files().create(body={"name": zp, "parents": [pid]}, media_body=MediaFileUpload(zp, chunksize=64 * 1024 * 1024, resumable=True), fields="id,size")
        resp = None; tries = 0
        while resp is None:
            try: _, resp = up.next_chunk()
            except Exception as e:
                tries += 1
                if tries > 8: raise
                import time; time.sleep(10 * tries)
        got = int(dr.files().get(fileId=resp["id"], fields="size").execute()["size"])
    os.remove(zp)
    if got != size: print("SIZE MISMATCH, kept on Kaggle:", ref, size, got, flush=True); fail += 1; continue
    rc, o = kg("kernels", "delete", ref, "-y")
    print(("archived+deleted " if rc == 0 else "archived, DELETE FAILED ") + ref, round(size / 1e6, 1), "MB", flush=True); ok += rc == 0; fail += rc != 0
print(f"SUMMARY key {key}: archived+deleted {ok}, kept {fail}")
