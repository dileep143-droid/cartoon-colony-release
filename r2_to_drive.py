# 10 Nov owner: "Use public repo just to transfer that's it and then delete them" -> old R2 files (s2work/) copied to Google Drive "BuBu TV Archive/R2/...".
# The file list (short-lived download links) arrives ENCRYPTED (data/r2move.enc); the key comes from the DRIVE_TOKEN secret, so nothing private shows in
# this public repo or its logs. Links and file contents are never printed. Deleting from R2 happens on the laptop only after Claude checks every copy.
#   python r2_to_drive.py data/r2move.enc
import base64, hashlib, json, os, sys, time, urllib.request
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
tok = json.loads(os.environ["DRIVE_TOKEN"])
blob = base64.b64decode(open(sys.argv[1]).read())
key = hashlib.sha256((tok["refresh_token"] + "|r2move").encode()).digest()
items = json.loads(AESGCM(key).decrypt(blob[:12], blob[12:], None))
c = Credentials.from_authorized_user_info(tok)
if not c.valid: c.refresh(Request())
dr = build("drive", "v3", credentials=c, cache_discovery=False)
_fold = {}
def folder(path):
    pid = None
    for i, nm in enumerate(path):
        k = "/".join(path[: i + 1])
        if k not in _fold:
            q = f"name='{nm}' and mimeType='application/vnd.google-apps.folder' and trashed=false" + (f" and '{pid}' in parents" if pid else " and 'root' in parents")
            f = dr.files().list(q=q, fields="files(id)").execute().get("files", [])
            _fold[k] = f[0]["id"] if f else dr.files().create(body={"name": nm, "mimeType": "application/vnd.google-apps.folder", **({"parents": [pid]} if pid else {})}, fields="id").execute()["id"]
        pid = _fold[k]
    return pid
ok = bad = 0
for it in items:
    parts = it["key"].split("/"); pid = folder(["BuBu TV Archive", "R2"] + parts[:-1]); name = parts[-1]
    have = dr.files().list(q=f"name='{name}' and '{pid}' in parents and trashed=false", fields="files(id,size)").execute().get("files", [])
    if any(int(h.get("size", -1)) == it["size"] for h in have):
        print(f"RESULT EXISTS {it['key']} {it['size']}", flush=True); ok += 1; continue
    tmp = "r2tmp.bin"
    try:
        for t in range(4):
            try:
                with urllib.request.urlopen(it["url"], timeout=300) as r, open(tmp, "wb") as f:
                    while True:
                        b = r.read(8 << 20)
                        if not b: break
                        f.write(b)
                if os.path.getsize(tmp) == it["size"]: break
            except Exception as e: print("download retry", t + 1, type(e).__name__, flush=True); time.sleep(10 * (t + 1))
        if not os.path.exists(tmp) or os.path.getsize(tmp) != it["size"]: raise RuntimeError("download incomplete")
        up = dr.files().create(body={"name": name, "parents": [pid]}, media_body=MediaFileUpload(tmp, chunksize=32 << 20, resumable=True), fields="id,size"); resp = None; tries = 0
        while resp is None:
            try: _, resp = up.next_chunk()
            except Exception as e:
                tries += 1
                if tries > 8: raise
                print("upload retry", tries, type(e).__name__, flush=True); time.sleep(10 * tries)
        if int(resp["size"]) != it["size"]: raise RuntimeError(f"size mismatch {resp['size']}")
        print(f"RESULT COPIED {it['key']} {it['size']}", flush=True); ok += 1
    except Exception as e:
        print(f"RESULT FAILED {it['key']} {str(e)[:120]}", flush=True); bad += 1
    finally:
        if os.path.exists(tmp): os.remove(tmp)
print(f"RESULT TOTAL ok={ok} failed={bad}")
