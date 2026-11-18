# 18 Nov owner: "set it up through github public repo please the collector ... send it to Google drive instead of r2 storage"
# Meta video links -> Google Drive "Mahabharatam Clips/<folder>/<item>_1.mp4" (DRIVE_TOKEN account), on GitHub Actions.
# The list (video links) arrives ENCRYPTED (data/clipfetch.enc); the key comes from the DRIVE_TOKEN secret, so no link shows in this public
# repo or its logs. Only counts are printed. The laptop deletes data/clipfetch.enc after each run. Files already in Drive are skipped.
#   python clip_fetch.py data/clipfetch.enc
import base64, hashlib, io, json, os, sys, time, urllib.request, threading
from concurrent.futures import ThreadPoolExecutor
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
tok = json.loads(os.environ["DRIVE_TOKEN"])
blob = base64.b64decode(open(sys.argv[1]).read())
J = json.loads(AESGCM(hashlib.sha256((tok["refresh_token"] + "|clipfetch").encode()).digest()).decrypt(blob[:12], blob[12:], None))
c = Credentials.from_authorized_user_info(tok)
if not c.valid: c.refresh(Request())
TL = threading.local()
def dr():
    if not hasattr(TL, "d"): TL.d = build("drive", "v3", credentials=c, cache_discovery=False)
    return TL.d
LOCK = threading.Lock(); FOLD = {}
def folder(name, parent):
    q = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false and '{parent}' in parents"
    f = dr().files().list(q=q, fields="files(id)").execute().get("files", [])
    return f[0]["id"] if f else dr().files().create(body={"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent]}, fields="id").execute()["id"]
def fid(sub):
    with LOCK:
        if "root" not in FOLD: FOLD["root"] = folder("Mahabharatam Clips", "root")
        if sub not in FOLD: FOLD[sub] = folder(sub, FOLD["root"])
        return FOLD[sub]
def one(x):
    err = ""; par = fid(x["f"]); name = f'{x["i"]}_1.mp4'
    if dr().files().list(q=f"name='{name}' and '{par}' in parents and trashed=false", fields="files(id)").execute().get("files"): return "ok"
    for t in range(3):
        try:
            b = urllib.request.urlopen(urllib.request.Request(x["url"], headers={"User-Agent": "Mozilla/5.0"}), timeout=120).read()
            if len(b) < 50000: raise Exception("too small")
            dr().files().create(body={"name": name, "parents": [par]}, media_body=MediaIoBaseUpload(io.BytesIO(b), mimetype="video/mp4", resumable=True), fields="id").execute()
            return "ok"
        except Exception as e: err = type(e).__name__; time.sleep(5)
    return "fail " + err
with ThreadPoolExecutor(6) as ex: r = list(ex.map(one, J))
print("RESULT ok", r.count("ok"), "of", len(r), "| fails:", {k: r.count(k) for k in set(r) if k != "ok"})
