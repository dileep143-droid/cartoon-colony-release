r"""Kaggle DATASETS -> Google Drive backup (owner 8 Nov: "copy to github and then to Google drive because our laptop is doing work").
python dataset_to_drive.py <list file> "<Drive folder>"
list file: one "<key number> <user/dataset>" per line. Each dataset is downloaded as one zip, uploaded as <user>__<dataset>.zip, then deleted
from the runner (disk stays small). Skips zips already in Drive. Needs env KAGGLE_KEYn + DRIVE_TOKEN."""
import json, os, subprocess, sys, time, glob, shutil
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
S = os.environ; lst, path = sys.argv[1], sys.argv[2]
c = Credentials.from_authorized_user_info(json.loads(S["DRIVE_TOKEN"]))
if not c.valid: c.refresh(Request())
dr = build("drive", "v3", credentials=c, cache_discovery=False)


def folder(nm, parent=None):
    q = f"name='{nm}' and mimeType='application/vnd.google-apps.folder' and trashed=false" + (f" and '{parent}' in parents" if parent else "")
    f = dr.files().list(q=q, fields="files(id)").execute().get("files", [])
    return f[0]["id"] if f else dr.files().create(body={"name": nm, "mimeType": "application/vnd.google-apps.folder", **({"parents": [parent]} if parent else {})}, fields="id").execute()["id"]


pid = None
for part in path.strip("/").split("/"): pid = folder(part, pid)
res = {}
for line in open(lst, encoding="utf-8"):
    if not line.strip() or line.startswith("#"): continue
    key, ref = line.split()[:2]; name = ref.replace("/", "__") + ".zip"
    if dr.files().list(q=f"name='{name}' and '{pid}' in parents and trashed=false", fields="files(id)").execute().get("files"):
        res[ref] = "already in Drive"; print(ref, "already in Drive", flush=True); continue
    env = dict(os.environ, KAGGLE_API_TOKEN=S[f"KAGGLE_KEY{key}"], PYTHONUTF8="1")
    shutil.rmtree("dl", ignore_errors=True); os.makedirs("dl")
    r = subprocess.run(["kaggle", "datasets", "download", ref, "-p", "dl"], env=env, capture_output=True, text=True)
    z = glob.glob("dl/*.zip")
    if not z:
        fs = [f for f in glob.glob("dl/**/*", recursive=True) if os.path.isfile(f)]
        if not fs: res[ref] = "DOWNLOAD FAILED " + (r.stdout + r.stderr)[-200:]; print(ref, res[ref], flush=True); continue
        shutil.make_archive("dl_pack", "zip", "dl"); z = ["dl_pack.zip"]
    up = dr.files().create(body={"name": name, "parents": [pid]}, media_body=MediaFileUpload(z[0], chunksize=64 * 1024 * 1024, resumable=True), fields="id,size")
    resp, tries = None, 0
    while resp is None:
        try: _, resp = up.next_chunk()
        except Exception as e:
            tries += 1
            if tries > 8: raise
            print("upload retry", tries, str(e)[-80:], flush=True); time.sleep(10 * tries)
    res[ref] = f"saved {resp.get('size')} bytes"; print(ref, res[ref], flush=True)
    for f in z: os.remove(f)
json.dump(res, open("backup_result.json", "w"), indent=1); print(json.dumps(res, indent=1))
if any(v.startswith("DOWNLOAD FAILED") for v in res.values()): sys.exit(1)
