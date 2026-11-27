# Mahabharatam long episodes -> Dileep Explains channels (27 Nov 2026; built from shorts_daily.py).
#   python mb_long.py <lang>     queue = data/mb/queue_<lang>.json (built on the laptop by build_queue.py)
# Rules: series order only (MB N goes up only when MB N-1 is already on the channel), never twice (an "| MB NN" long title already on the channel = done),
# private + publishAt = the queue's 19:00 IST slot; if that is before max(now+30 min, MB N-1's publish time + 20 h) it moves to the next 19:00 IST
# after that (never two on one day, never before MB N-1).
# Master comes from R2 (or Google Drive for the 24 Nov Drive-only fixed masters); ffprobe duration must match the build timing (+-8 s) or it stops.
# Thumbnail must exist in R2 before upload; thumbnails.set failure (unverified channel) is reported THUMB_FAIL - NOT retried automatically:
# dispatch mb-long with thumbs_only=1 after the channel is verified.
# Every upload is read back (privacy, publishAt, madeForKids, synthetic media, upload status). Quota / upload-limit error -> channel stops, loud RESULT line.
# Nothing secret is printed.
import datetime, io, json, os, re, subprocess, sys, time
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import boto3
from botocore.config import Config
code = sys.argv[1]
EXPECT = {"te": "UC2eTiq2nEmcU7udbcivCI5A", "hi": "UC-VXLBB5DbU5A6h3zroABrA", "ta": "UCYMgVtA27zUBsK0Tp2QGtVw",
          "en": "UCQZPvuz9zgLYOjiItiw23Tw", "bn": "UC4WGHUAAhMsP3AETl61TAQw"}
DRY = os.environ.get("DRY", "1") != "0"
MAX = int(os.environ.get("MAX") or 1)
ONLY = [x.strip() for x in (os.environ.get("ONLY") or "").split(",") if x.strip()]
THUMBS_ONLY = os.environ.get("THUMBS_ONLY") == "1"
BUCKET = "eduorbex-media"
Q = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "mb", f"queue_{code}.json"), encoding="utf-8"))
queue, CAT = Q["items"], Q["category"]
def out(*a): print("RESULT", code, *a, flush=True)
def clean(e):
    s = re.sub(r"https?://\S+", "<link>", str(e))
    return s.replace(os.environ.get("CF_R2_ENDPOINT") or "#none#", "R2")[-300:]
def creds(js):
    c = Credentials.from_authorized_user_info(json.loads(js))
    if not c.valid: c.refresh(Request())
    return c
def retry(fn, n=4):
    for k in range(n):
        try: return fn()
        except Exception as e:
            if "quota" in str(e).lower() or k == n - 1: raise
            print("retry", k + 1, clean(e)[-120:], flush=True); time.sleep(15 * (k + 1))
yt = build("youtube", "v3", credentials=creds(os.environ["YT_TOKEN"]), cache_discovery=False)
S3 = boto3.client("s3", endpoint_url=os.environ["CF_R2_ENDPOINT"], aws_access_key_id=os.environ["CF_R2_ACCESS_KEY_ID"],
                  aws_secret_access_key=os.environ["CF_R2_SECRET_ACCESS_KEY"], region_name="auto", config=Config(signature_version="s3v4"))
ch = retry(lambda: yt.channels().list(part="contentDetails,status", mine=True).execute())["items"][0]
me, up = ch["id"], ch["contentDetails"]["relatedPlaylists"]["uploads"]
longok = ch.get("status", {}).get("longUploadsStatus")
out("token OK, channel", "MATCH" if me == EXPECT.get(code) else "MISMATCH (wrong token!)", "| longUploadsStatus:", longok)
if me != EXPECT.get(code): sys.exit(1)
MBRE = re.compile(r"\|\s*MB\s*(\d{2})\b")
def on_channel():
    have, tok = {}, None
    while True:
        r = retry(lambda: yt.playlistItems().list(part="snippet,contentDetails", playlistId=up, maxResults=50, pageToken=tok).execute())
        for i in r["items"]:
            t = i["snippet"]["title"]
            m = MBRE.search(t)
            if m and "#shorts" not in t.lower(): have.setdefault(int(m.group(1)), i["contentDetails"]["videoId"])
        tok = r.get("nextPageToken")
        if not tok: return have
have = on_channel(); done_here = {}
out("long MB already on channel:", sorted(have), "| queue:", [q["mb"] for q in queue])

def r2_get(key, path): S3.download_file(BUCKET, key, path)
def drive_get(fid, path):
    last = None
    for env in ("DRIVE_TOKEN", "DRIVE_TOKEN_5TB"):
        if not os.environ.get(env): continue
        try:
            d = build("drive", "v3", credentials=creds(os.environ[env]), cache_discovery=False)
            with open(path, "wb") as fh:
                dl = MediaIoBaseDownload(fh, d.files().get_media(fileId=fid, supportsAllDrives=True), chunksize=64 * 2**20); ok = False
                while not ok: _, ok = dl.next_chunk()
            if os.path.getsize(path) > 50_000_000: return
        except Exception as e: last = e
    raise Exception("drive download failed: " + clean(last))
def dur(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)
def set_thumb(vid, q):
    p = "thumb.jpg"; S3.download_file(BUCKET, q["thumb"], p)
    try: retry(lambda: yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(p, mimetype="image/jpeg")).execute(), n=2); return "thumb OK"
    except Exception as e: return "THUMB_FAIL " + clean(e)[-160:]
    finally: os.remove(p)

if THUMBS_ONLY:
    for q in queue:
        if q["mb"] in have and (not ONLY or q["id"] in ONLY): out(q["id"], have[q["mb"]], set_thumb(have[q["mb"]], q))
    sys.exit(0)

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
def _p(t): return datetime.datetime.strptime(t[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
def slot_for(planned, prev_t, now):
    """planned slot unless it is before floor = max(now + 30 min, MB N-1 publish + 20 h); then the next 19:00 IST at/after floor."""
    floor = now + datetime.timedelta(minutes=30)
    if prev_t: floor = max(floor, _p(prev_t) + datetime.timedelta(hours=20))
    pl = _p(planned)
    if pl >= floor: return planned
    d0 = floor.astimezone(IST); c = datetime.datetime(d0.year, d0.month, d0.day, 19, 0, tzinfo=IST)
    if c < floor: c += datetime.timedelta(days=1)
    return c.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
dry_pub = {}
now = datetime.datetime.now(datetime.timezone.utc); n_up = 0
for q in queue:
    if ONLY and q["id"] not in ONLY: continue
    if n_up >= MAX: break
    mb = q["mb"]
    if mb in have or mb in done_here: continue
    if mb > 0 and (mb - 1) not in have and (mb - 1) not in done_here:
        out(q["id"], f"WAIT - MB {mb - 1:02d} is not on the channel yet (series order)"); break
    try: S3.head_object(Bucket=BUCKET, Key=q["thumb"])
    except Exception: out(q["id"], "WAIT - thumbnail not in R2 yet"); break
    if q["expect_dur"] > 900 and longok != "allowed":
        out(q["id"], f"BLOCKED - {q['expect_dur'] / 60:.1f} min > 15 min and channel longUploadsStatus={longok} (owner must verify the channel by phone)"); break
    prev_t = None                                           # publish time of MB N-1 on this channel
    pv = done_here.get(mb - 1) or have.get(mb - 1)
    if pv and pv != "dry":
        try:
            pvv = retry(lambda: yt.videos().list(part="status,snippet", id=pv).execute())["items"][0]
            prev_t = pvv["status"].get("publishAt") or pvv["snippet"]["publishedAt"]
        except Exception: prev_t = None
    elif pv == "dry": prev_t = dry_pub.get(mb - 1)
    newpub = slot_for(q["publishAt"], prev_t, now)
    if newpub != q["publishAt"]: out(q["id"], "slot", q["publishAt"], "-> moved to", newpub, "(one per day, after MB N-1)")
    q = dict(q, publishAt=newpub); dry_pub[mb] = newpub; late = False
    path = "ep.mp4"
    try:
        if q.get("r2"): r2_get(q["r2"], path)
        else: drive_get(q["drive"], path)
    except Exception as e: out(q["id"], "DOWNLOAD FAILED", clean(e)); break
    d = dur(path)
    if abs(d - q["expect_dur"]) > 8:
        out(q["id"], f"STOP - duration {d:.1f}s does not match build {q['expect_dur']}s (wrong file?)"); os.remove(path); break
    sz = os.path.getsize(path) // 1_000_000
    have = on_channel()                                     # re-check right before the insert
    if mb in have: out(q["id"], "already on channel (found on re-check)", have[mb]); os.remove(path); continue
    st = {"privacyStatus": "public"} if late else {"privacyStatus": "private", "publishAt": q["publishAt"]}
    st.update({"selfDeclaredMadeForKids": False, "embeddable": True, "containsSyntheticMedia": True})
    sn = {"title": q["title"][:100], "description": q["description"][:5000], "tags": q["tags"], "categoryId": CAT,
          "defaultLanguage": code, "defaultAudioLanguage": code}
    if DRY:
        out(q["id"], f"DRY ok | {d:.1f}s {sz} MB | {'PUBLIC on processing (slot passed)' if late else 'private, publishAt ' + q['publishAt']} | {sn['title']}")
        os.remove(path); done_here[mb] = "dry"; n_up += 1; continue
    try:
        req = yt.videos().insert(part="snippet,status", body={"snippet": sn, "status": st},
                                 media_body=MediaFileUpload(path, chunksize=32 * 2**20, resumable=True)); res = None
        while res is None: _, res = req.next_chunk()
    except Exception as e:
        os.remove(path)
        out(q["id"], "STOPPED", "QUOTA/UPLOAD LIMIT - resume next run" if re.search(r"quota|uploadLimit|rateLimit", str(e), re.I) else "", clean(e)); break
    os.remove(path); vid = res["id"]; done_here[mb] = vid; n_up += 1
    th = set_thumb(vid, q)
    time.sleep(5)
    v = retry(lambda: yt.videos().list(part="snippet,status", id=vid).execute())["items"][0]; s = v["status"]
    ok = (s.get("uploadStatus") not in ("rejected", "failed") and s.get("madeForKids") is False and res.get("status", {}).get("containsSyntheticMedia") is True
          and (s.get("privacyStatus") == "public" if late else (s.get("privacyStatus") == "private" and s.get("publishAt", "").startswith(q["publishAt"][:16]))))
    out(q["id"], "UPLOADED", vid, "| readback", "OK" if ok else "CHECK!", json.dumps({**{k: s.get(k) for k in ("uploadStatus", "privacyStatus", "publishAt", "madeForKids")}, "synthetic(insert)": res.get("status", {}).get("containsSyntheticMedia")}),
        "|", th, "|", v["snippet"]["title"])
    print("UPLOAD_JSON " + json.dumps({"id": q["id"], "video": vid, "channel": me, "lang": code, "mb": mb, "publishAt": s.get("publishAt") or ("public now" if late else None),
                                      "privacy": s.get("privacyStatus"), "title": v["snippet"]["title"], "thumb": th[:10], "readback_ok": ok}, ensure_ascii=False), flush=True)
left = [q["id"] for q in queue if q["mb"] not in have and q["mb"] not in done_here]
out(f"{'DRY ' if DRY else ''}done this run: {n_up}, still to upload: {len(left)} {left[:4]}")
