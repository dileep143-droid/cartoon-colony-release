# BuBu TV daily song timer (owner 3 Nov 2026): Google Drive -> YouTube, 5 new songs per channel per day, going public at 07:00 10:00 13:00 16:00 19:00 IST.
#   python song_daily.py <code>      (one language channel; GitHub matrix runs all 20)
# Queue = data/songs/queue.json (only songs Claude checked). A song counts as done on a channel when a video with its exact title exists there,
# so re-runs never duplicate. Quota/upload errors stop this channel for today; the next day continues where it stopped.
import datetime, io, json, os, sys, time
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
code = sys.argv[1]; PER_DAY = 5; SLOTS_IST = [7, 10, 13, 16, 19]
NAME = {"hi": "hindi", "te": "telugu", "ta": "tamil", "kn": "kannada", "ml": "malayalam", "mr": "marathi", "bn": "bengali", "gu": "gujarati", "pa": "punjabi", "or": "odia",
        "as": "assamese", "en": "english", "ne": "nepali", "ur": "urdu", "sd": "sindhi", "mai": "maithili", "hry": "haryanvi", "ks": "kashmiri", "mni": "manipuri", "bho": "bhojpuri"}
NEW = {"ne", "ur", "sd", "mai", "hry", "ks", "mni", "bho"}; YT_LANG = {"ne": "ne", "ur": "ur"}
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "songs")
queue = json.load(open(os.path.join(D, "queue.json")))["songs"]
def creds(env):
    c = Credentials.from_authorized_user_info(json.loads(os.environ[env]))
    if not c.valid: c.refresh(Request())
    return c
def retry(fn, n=5):
    for k in range(n):
        try: return fn()
        except Exception as e:
            if "quota" in str(e).lower() or k == n - 1: raise
            print("retry", k + 1, str(e)[-120:], flush=True); time.sleep(20 * (k + 1))
yt = build("youtube", "v3", credentials=creds("YT_TOKEN"), cache_discovery=False)
dr = build("drive", "v3", credentials=creds("DRIVE_TOKEN"), cache_discovery=False)
up = retry(lambda: yt.channels().list(part="contentDetails", mine=True).execute())["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
have, tok = set(), None
while True:                                               # every title already on the channel (public, private or scheduled)
    r = retry(lambda: yt.playlistItems().list(part="snippet", playlistId=up, maxResults=50, pageToken=tok).execute())
    have |= {i["snippet"]["title"].strip() for i in r["items"]}; tok = r.get("nextPageToken")
    if not tok or len(have) > 400: break
now = datetime.datetime.now(datetime.timezone.utc); ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
today = now.astimezone(ist).date()
slots = [datetime.datetime(today.year, today.month, today.day, h, 0, tzinfo=ist) for h in SLOTS_IST]
slots = [max(s, now + datetime.timedelta(minutes=40)) for s in slots]       # GitHub timers can start late -> never schedule in the past
def drive_file(slug, name):
    q = f"name='{name}' and trashed=false"
    for f in retry(lambda: dr.files().list(q=q, fields="files(id,parents)").execute()).get("files", []):
        par = retry(lambda: dr.files().get(fileId=f["parents"][0], fields="name").execute())["name"]
        if par == slug: return f["id"]
    return None
done = 0
for slug in queue:
    if done >= PER_DAY: break
    mp = os.path.join(D, slug, f"meta_{code}.json")
    if not os.path.exists(mp): continue
    meta = json.load(open(mp, encoding="utf-8")); title = meta["title"][:100].strip()
    if title in have: continue
    fid = drive_file(slug, f"{slug[:3]}_{NAME[code]}.mp4")
    if not fid: print(f"RESULT {code} {slug} NOT_IN_DRIVE"); continue
    path = f"{slug}_{code}.mp4"; fh = io.FileIO(path, "wb"); dl = MediaIoBaseDownload(fh, dr.files().get_media(fileId=fid), chunksize=64 * 2**20); ok = False
    while not ok: _, ok = dl.next_chunk()
    fh.close()
    pub = slots[done].astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sn = {"title": title, "description": meta["description"][:5000], "tags": meta["tags"][:30], "categoryId": "27"}
    yl = code if code not in NEW else YT_LANG.get(code)
    if yl: sn.update({"defaultLanguage": yl, "defaultAudioLanguage": yl})
    body = {"snippet": sn, "status": {"privacyStatus": "private", "publishAt": pub, "selfDeclaredMadeForKids": True, "embeddable": True, "containsSyntheticMedia": True}}
    try:
        req = yt.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(path, chunksize=16 * 2**20, resumable=True)); res = None
        while res is None: _, res = req.next_chunk()
    except Exception as e:
        print(f"RESULT {code} {slug} STOPPED {str(e)[-200:]}"); break             # quota or upload limit -> continue tomorrow
    vid = res["id"]; done += 1; have.add(title); os.remove(path)
    th = os.path.join(D, slug, f"thumb_{code}.jpg")
    try: yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(th, mimetype="image/jpeg")).execute(); t = "thumb ok"
    except Exception as e: t = "thumb FAILED"
    print(f"RESULT {code} {slug} SCHEDULED {vid} public {pub} | {t}", flush=True)
print(f"RESULT {code} done today: {done}")
