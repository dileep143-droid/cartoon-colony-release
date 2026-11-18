# 18 Nov owner: "set it up through github public repo please the collector" -> Meta video links -> R2, run on GitHub Actions instead of Kaggle.
# The list (video links + short-lived R2 upload links) arrives ENCRYPTED (data/clipfetch.enc); the key comes from the DRIVE_TOKEN secret, so no link
# shows in this public repo or its logs. Only counts are printed. The laptop deletes data/clipfetch.enc after each run.
#   python clip_fetch.py data/clipfetch.enc
import base64, hashlib, json, os, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
tok = json.loads(os.environ["DRIVE_TOKEN"])
blob = base64.b64decode(open(sys.argv[1]).read())
J = json.loads(AESGCM(hashlib.sha256((tok["refresh_token"] + "|clipfetch").encode()).digest()).decrypt(blob[:12], blob[12:], None))
def one(x):
    err = ""
    for t in range(3):
        try:
            b = urllib.request.urlopen(urllib.request.Request(x["url"], headers={"User-Agent": "Mozilla/5.0"}), timeout=120).read()
            if len(b) < 50000: raise Exception("too small")
            urllib.request.urlopen(urllib.request.Request(x["put"], data=b, method="PUT", headers={"Content-Type": "video/mp4"}), timeout=180).read()
            return "ok"
        except Exception as e: err = type(e).__name__; time.sleep(5)
    return "fail " + err
with ThreadPoolExecutor(8) as ex: r = list(ex.map(one, J))
print("RESULT ok", r.count("ok"), "of", len(r), "| fails:", {k: r.count(k) for k in set(r) if k != "ok"})
