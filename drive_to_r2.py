# 18 Nov owner: corrected (age-fixed) Mahabharatam clips live in Google Drive "Mahabharatam Clips/<folder>/"; the episode builder reads R2.
# This copies the listed Drive files into R2 for the build (Drive -> GitHub -> R2), so the laptop downloads nothing.
# The list (Drive file ids + 6-hour R2 upload links) arrives ENCRYPTED (data/drive2r2.enc); key from the DRIVE_TOKEN secret. Only counts are printed.
#   python drive_to_r2.py data/drive2r2.enc
import base64, hashlib, io, json, os, sys, time, urllib.request, threading
from concurrent.futures import ThreadPoolExecutor
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
tok = json.loads(os.environ["DRIVE_TOKEN"])
blob = base64.b64decode(open(sys.argv[1]).read())
J = json.loads(AESGCM(hashlib.sha256((tok["refresh_token"] + "|drive2r2").encode()).digest()).decrypt(blob[:12], blob[12:], None))
c = Credentials.from_authorized_user_info(tok)
if not c.valid: c.refresh(Request())
TL = threading.local()
def dr():
    if not hasattr(TL, "d"): TL.d = build("drive", "v3", credentials=c, cache_discovery=False)
    return TL.d
def one(x):
    err = ""
    for t in range(3):
        try:
            buf = io.BytesIO(); d = MediaIoBaseDownload(buf, dr().files().get_media(fileId=x["id"])); ok = False
            while not ok: _, ok = d.next_chunk()
            b = buf.getvalue()
            if len(b) < 50000: raise Exception("too small")
            urllib.request.urlopen(urllib.request.Request(x["put"], data=b, method="PUT", headers={"Content-Type": "video/mp4"}), timeout=180).read()
            return "ok"
        except Exception as e: err = type(e).__name__; time.sleep(5)
    return "fail " + err
with ThreadPoolExecutor(6) as ex: r = list(ex.map(one, J))
print("RESULT ok", r.count("ok"), "of", len(r), "| fails:", {k: r.count(k) for k in set(r) if k != "ok"})
