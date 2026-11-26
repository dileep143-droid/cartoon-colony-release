# Dileep Explains -> Instagram Reels (26 Nov 2026). Same idea as shorts_daily.py (YouTube):
#   python ig_daily.py <te|hi|en>     env: IG_TOKEN, DRY (1 = test, default), PER_RUN (Reels to post this run, default 1), R2 secrets
# Queue: data/ig/queue_<lang>.json (built on the laptop by E:/mb_builds/shorts_v1/ig_queue.py from the YouTube queue + trending extras).
# Each item: id, r2 (video key), caption (Instagram style). Never posts twice: a Reel is skipped if a post on the account already
# starts with the same first caption line. Official Instagram API (Instagram Login): container -> wait FINISHED -> publish.
# Logs show only channel, time, first caption line and status; never tokens or links.
import json, os, sys, time, urllib.parse, urllib.request, urllib.error
import boto3
from botocore.config import Config
lang = sys.argv[1]; TOK = os.environ["IG_TOKEN"]; DRY = os.environ.get("DRY", "1") != "0"
PER_RUN = max(1, int(os.environ.get("PER_RUN") or 1)); G = "https://graph.instagram.com/v21.0"
S3 = boto3.client("s3", endpoint_url=os.environ["CF_R2_ENDPOINT"], aws_access_key_id=os.environ["CF_R2_ACCESS_KEY_ID"],
                  aws_secret_access_key=os.environ["CF_R2_SECRET_ACCESS_KEY"], region_name="auto", config=Config(signature_version="s3v4"))
def log(*a): print("RESULT", lang, *a, flush=True)
def call(method, path, params=None):
    params = dict(params or {}, access_token=TOK); url = G + path
    if method == "GET": req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params))
    else: req = urllib.request.Request(url, data=urllib.parse.urlencode(params).encode(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=120) as r: return json.loads(r.read())
    except urllib.error.HTTPError as e:
        msg = e.read().decode("utf-8", "ignore")
        try: msg = json.loads(msg)["error"].get("message", msg)
        except Exception: pass
        raise RuntimeError(f"HTTP {e.code}: {str(msg)[:160]}") from None
me = call("GET", "/me", {"fields": "username,account_type"}); log("account", me.get("username"), me.get("account_type"))
posted = set(); nxt = {"fields": "caption", "limit": 100}
for _ in range(5):
    r = call("GET", "/me/media", nxt)
    for m in r.get("data", []): posted.add((m.get("caption") or "").split("\n")[0].strip())
    cur = r.get("paging", {}).get("cursors", {}).get("after")
    if not cur or not r.get("paging", {}).get("next"): break
    nxt = {"fields": "caption", "limit": 100, "after": cur}
q = json.load(open(f"data/ig/queue_{lang}.json", encoding="utf-8"))["items"]
todo = [i for i in q if i["caption"].split("\n")[0].strip() not in posted]
log(f"queue {len(q)}, already posted {len(q) - len(todo)}, left {len(todo)}")
done = 0
for it in todo:
    if done >= PER_RUN: break
    first = it["caption"].split("\n")[0][:70]
    if DRY: log("DRY would post |", first, "|", it["r2"].split("/")[-1]); done += 1; continue
    url = S3.generate_presigned_url("get_object", Params={"Bucket": "eduorbex-media", "Key": it["r2"]}, ExpiresIn=6 * 3600)
    try:
        c = call("POST", "/me/media", {"media_type": "REELS", "video_url": url, "caption": it["caption"], "share_to_feed": "true"})
        cid = c["id"]; st = ""
        for _ in range(60):                                  # Instagram downloads + processes the video (usually 1-3 min)
            time.sleep(15); st = call("GET", f"/{cid}", {"fields": "status_code,status"}).get("status_code", "")
            if st in ("FINISHED", "ERROR", "EXPIRED"): break
        if st != "FINISHED": log("NOT POSTED", first, "| container status", st); continue
        p = call("POST", "/me/media_publish", {"creation_id": cid})
        log("POSTED", first, "| media", p.get("id")); done += 1
    except Exception as e:
        log("ERROR", first, "|", str(e)[:200])
        if "limit" in str(e).lower(): break                  # publishing limit (50 per 24 h) -> stop for today
log("done", done, "| still waiting", max(0, len(todo) - done))
