# Dileep Explains daily Shorts timer (22 Nov 2026, adapted from song_daily.py): R2 -> YouTube, N Shorts per channel per day (default 1),
# scheduled private + publishAt at fixed IST slots (1/day: 18:30; 2/day: 12:30 + 18:30).
#   python shorts_daily.py <lang>      (te hi ta en bn; the GitHub matrix runs all 5)
# Queue = data/shorts/queue_<lang>.json (built on the laptop by E:/mb_builds/shorts_v1/queue_shorts.py). A Short counts as done when a video with
# its exact title exists on the channel (public, private or scheduled) -> re-runs never duplicate. Quota/upload errors stop this channel for today.
# After the upload the pinned-question text is posted as a top-level comment (the owner pins it by hand; the API cannot pin). If that fails
# (e.g. video still private), every later run re-tries it once the video is public. Nothing secret (tokens, links) is ever printed.
# DRY=1: everything except videos.insert / commentThreads.insert; DAYS=n (dry only) projects the next n days' schedule.
import datetime, json, os, re, sys, time
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import boto3
from botocore.config import Config
code = sys.argv[1]
EXPECT = {"te": "UC2eTiq2nEmcU7udbcivCI5A", "hi": "UC-VXLBB5DbU5A6h3zroABrA", "ta": "UCYMgVtA27zUBsK0Tp2QGtVw",
          "en": "UCQZPvuz9zgLYOjiItiw23Tw", "bn": "UC4WGHUAAhMsP3AETl61TAQw"}
DRY = os.environ.get("DRY", "1") != "0"            # safe default: dry unless the workflow says dry=0
PER_DAY = max(1, int(os.environ.get("PER_DAY") or 1))
DAYS = max(1, int(os.environ.get("DAYS") or 1)) if DRY else 1
if os.environ.get("SLOTS"): SLOTS_IST = [tuple(int(x) for x in s.split(":")) for s in os.environ["SLOTS"].split(",")]
else: SLOTS_IST = [(18, 30)] if PER_DAY == 1 else [(12, 30), (18, 30)] if PER_DAY == 2 else [(9 + 3 * k, 30) for k in range(PER_DAY)]
PER_DAY = min(PER_DAY, len(SLOTS_IST))
BUCKET = "eduorbex-media"
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "shorts")
queue = json.load(open(os.path.join(D, f"queue_{code}.json"), encoding="utf-8"))["items"]
def clean(e):   # error text without links or the R2 endpoint
    s = re.sub(r"https?://\S+", "<link>", str(e))
    return s.replace(os.environ.get("CF_R2_ENDPOINT") or "#none#", "R2")[-200:]
def creds(env):
    c = Credentials.from_authorized_user_info(json.loads(os.environ[env]))
    if not c.valid: c.refresh(Request())
    return c
def retry(fn, n=5):
    for k in range(n):
        try: return fn()
        except Exception as e:
            if "quota" in str(e).lower() or k == n - 1: raise
            print("retry", k + 1, clean(e)[-120:], flush=True); time.sleep(20 * (k + 1))
yt = build("youtube", "v3", credentials=creds("YT_TOKEN"), cache_discovery=False)
S3 = boto3.client("s3", endpoint_url=os.environ["CF_R2_ENDPOINT"], aws_access_key_id=os.environ["CF_R2_ACCESS_KEY_ID"],
                  aws_secret_access_key=os.environ["CF_R2_SECRET_ACCESS_KEY"], region_name="auto", config=Config(signature_version="s3v4"))
ch = retry(lambda: yt.channels().list(part="contentDetails", mine=True).execute())["items"][0]
me = ch["id"]; up = ch["contentDetails"]["relatedPlaylists"]["uploads"]
print(f"RESULT {code} token OK, channel {'MATCH' if me == EXPECT.get(code) else 'MISMATCH (wrong token for this language!)'}", flush=True)
if me != EXPECT.get(code): sys.exit(1)
have, ids, tok = {}, [], None
while True:                                               # every title already on the channel (public, private or scheduled)
    r = retry(lambda: yt.playlistItems().list(part="snippet,contentDetails", playlistId=up, maxResults=50, pageToken=tok).execute())
    for i in r["items"]: have[i["snippet"]["title"].strip()] = i["contentDetails"]["videoId"]
    tok = r.get("nextPageToken")
    if not tok or len(have) > 1000: break
print(f"RESULT {code} channel has {len(have)} videos, queue {len(queue)}, {sum(q['title'] in have for q in queue)} of them already on the channel", flush=True)

def comment(vid, text):
    yt.commentThreads().insert(part="snippet", body={"snippet": {"videoId": vid, "topLevelComment": {"snippet": {"textOriginal": text}}}}).execute()

# 1) comments that could not be posted earlier (video was still private) -> post once the video is public and has no comment from us
qt = {q["title"]: q for q in queue if q["title"] in have}
vids = [have[t] for t in qt]
for k in range(0, len(vids), 50):
    for v in retry(lambda: yt.videos().list(part="snippet,status", id=",".join(vids[k:k + 50])).execute())["items"]:
        if v["status"].get("privacyStatus") != "public": continue
        q = qt.get(v["snippet"]["title"].strip())
        if not q: continue
        try:
            th = retry(lambda: yt.commentThreads().list(part="snippet", videoId=v["id"], maxResults=100, textFormat="plainText").execute())["items"]
        except Exception as e: print(f"RESULT {code} {q['id']} comment check failed {clean(e)}"); continue
        if any(t["snippet"]["topLevelComment"]["snippet"].get("authorChannelId", {}).get("value") == me for t in th): continue
        if DRY: print(f"RESULT {code} {q['id']} DRY would post the missing question comment", flush=True); continue
        try: comment(v["id"], q["comment"]); print(f"RESULT {code} {q['id']} question comment posted (pin it by hand)", flush=True)
        except Exception as e: print(f"RESULT {code} {q['id']} comment FAILED {clean(e)}")

# 2) today's uploads
now = datetime.datetime.now(datetime.timezone.utc); ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
today = now.astimezone(ist).date()
done_total = 0; stopped = False
for day in range(DAYS):
    d = today + datetime.timedelta(days=day)
    slots = [datetime.datetime(d.year, d.month, d.day, h, m, tzinfo=ist) for h, m in SLOTS_IST]
    slots = [max(s, now + datetime.timedelta(minutes=40)) for s in slots]       # GitHub timers can start late -> never schedule in the past
    done = 0
    for q in queue:
        if done >= PER_DAY or stopped: break
        title = q["title"][:100].strip()
        if title in have: continue
        if any(x in q["id"] for x in ("cow", "amb")): continue                   # never these (owner)
        key = q["r2"]; path = os.path.basename(key)
        try: size = S3.head_object(Bucket=BUCKET, Key=key)["ContentLength"]
        except Exception as e: print(f"RESULT {code} {q['id']} NOT_IN_R2 - skipped, next Short", flush=True); continue
        when = slots[done].astimezone(ist)
        if DRY:
            if day == 0:                                                         # real download only for today's item(s)
                S3.download_file(BUCKET, key, path); size = os.path.getsize(path); os.remove(path)
            print(f"RESULT {code} DRY | {when:%a %d %b %Y %H:%M} IST | {title} | {size // 1_000_000} MB | comment: {q['comment'][:60]}", flush=True)
            done += 1; done_total += 1; have[title] = "dry"; continue
        try: S3.download_file(BUCKET, key, path)
        except Exception as e: print(f"RESULT {code} {q['id']} R2 DOWNLOAD FAILED {clean(e)}"); continue
        if os.path.getsize(path) < 1_000_000: print(f"RESULT {code} {q['id']} FILE TOO SMALL - skipped"); os.remove(path); continue
        pub = slots[done].astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        sn = {"title": title, "description": q["description"][:5000], "tags": q["tags"][:30], "categoryId": "27",
              "defaultLanguage": code, "defaultAudioLanguage": code}
        body = {"snippet": sn, "status": {"privacyStatus": "private", "publishAt": pub, "selfDeclaredMadeForKids": False, "embeddable": True,
                                          "containsSyntheticMedia": True}}
        try:
            req = yt.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(path, chunksize=16 * 2**20, resumable=True)); res = None
            while res is None: _, res = req.next_chunk()
        except Exception as e:
            print(f"RESULT {code} {q['id']} STOPPED {clean(e)}"); os.remove(path); stopped = True; break     # quota or upload limit -> continue tomorrow
        vid = res["id"]; done += 1; done_total += 1; have[title] = vid; os.remove(path)
        try: comment(vid, q["comment"]); c = "question comment posted (pin it by hand)"
        except Exception as e: c = "comment not yet possible, will retry when public (" + clean(e)[-80:] + ")"
        print(f"RESULT {code} {q['id']} SCHEDULED {when:%d %b %H:%M} IST | {title} | {c}", flush=True)
    if stopped: break
left = sum(1 for q in queue if q["title"][:100].strip() not in have)
print(f"RESULT {code} {'DRY ' if DRY else ''}done: {done_total}, still waiting in queue: {left}{' - QUEUE EMPTY, add more Shorts' if left == 0 else ''}")
