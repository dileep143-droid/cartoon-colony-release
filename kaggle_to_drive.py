r"""Kaggle -> GitHub -> Google Drive (owner 2 Nov: finished videos go straight to Drive, the laptop is not needed).
Waits for a Kaggle kernel to finish, downloads its output files, copies each to the Drive folder (made if missing), skips files already there.
python kaggle_to_drive.py <kernel id> <key number> "<Drive folder, e.g. BuBu TV Songs/S02_amma_rotis>" [file regex, default \.mp4$]"""
import json, os, re, subprocess, sys, time
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
kernel, key, path = sys.argv[1], sys.argv[2], sys.argv[3]; pat = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else r"\.mp4$"
env = dict(os.environ, KAGGLE_API_TOKEN=os.environ.get("KAGGLE_ONE") or os.environ[f"KAGGLE_KEY{key}"], PYTHONUTF8="1")
for i in range(300):                                         # up to 5 hours
    st = subprocess.run(["kaggle", "kernels", "status", kernel], env=env, capture_output=True, text=True).stdout.strip(); print(st, flush=True)
    if not re.search(r"RUNNING|QUEUED", st, re.I): break
    time.sleep(60)
if "COMPLETE" not in st.upper(): sys.exit("kernel did not finish OK: " + st)
os.makedirs("dl", exist_ok=True)
r = subprocess.run(["kaggle", "kernels", "output", kernel, "-p", "dl"], env=env, capture_output=True, text=True); print(r.stdout[-500:], r.stderr[-500:])
files = sorted(f for f in os.listdir("dl") if re.search(pat, f))
if not files: sys.exit("no output files match " + pat)
c = Credentials.from_authorized_user_info(json.loads(os.environ["DRIVE_TOKEN"]))
if not c.valid: c.refresh(Request())
dr = build("drive", "v3", credentials=c, cache_discovery=False)
def folder(nm, parent=None):
    q = f"name='{nm}' and mimeType='application/vnd.google-apps.folder' and trashed=false" + (f" and '{parent}' in parents" if parent else "")
    f = dr.files().list(q=q, fields="files(id)").execute().get("files", [])
    return f[0]["id"] if f else dr.files().create(body={"name": nm, "mimeType": "application/vnd.google-apps.folder", **({"parents": [parent]} if parent else {})}, fields="id").execute()["id"]
pid = None
for part in path.strip("/").split("/"): pid = folder(part, pid)
res = {}
for f in files:
    if dr.files().list(q=f"name='{f}' and '{pid}' in parents and trashed=false", fields="files(id)").execute().get("files"):
        res[f] = "already there"; print(f, "already in Drive", flush=True); continue
    up = dr.files().create(body={"name": f, "parents": [pid]}, media_body=MediaFileUpload(os.path.join("dl", f), chunksize=64 * 1024 * 1024, resumable=True), fields="id,size")
    resp = None
    while resp is None: _, resp = up.next_chunk()
    res[f] = resp["id"]; print(f, "saved to Drive", resp.get("size"), flush=True)
print(json.dumps({"kernel": kernel, "folder": path, "files": res}))
